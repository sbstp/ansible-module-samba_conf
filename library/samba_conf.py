from __future__ import absolute_import, division, print_function
import copy
import re

from ansible.module_utils.basic import AnsibleModule


__metaclass__ = type

DOCUMENTATION = r"""
---
module: samba_conf

short_description: Edit samba configuration

# If this is part of a collection, you need to use semantic versioning,
# i.e. the version is of the form "2.5.0" and not "2.4".
version_added: "1.0.0"

description: This is my longer description explaining my test module.

options:
    name:
        description: This is the message to send to the test module.
        required: true
        type: str
    new:
        description:
            - Control to demo if the result of this module is changed or not.
            - Parameter description can be a list as well.
        required: false
        type: bool
# Specify this value according to your collection
# in format of namespace.collection.doc_fragment_name
# extends_documentation_fragment:
#     - my_namespace.my_collection.my_doc_fragment_name

author:
    - Simon Bernier St-Pierre (@sbstp)
"""

EXAMPLES = r"""
# Pass in a message
- name: Test with a message
  my_namespace.my_collection.my_test:
    name: hello world

# pass in a message and have changed true
- name: Test with a message and changed output
  my_namespace.my_collection.my_test:
    name: hello world
    new: true

# fail the module
- name: Test failure of the module
  my_namespace.my_collection.my_test:
    name: fail me
"""

RETURN = r"""
# These are examples of possible return values, and in general should use other names for return values.
original_message:
    description: The original name param that was passed in.
    type: str
    returned: always
    sample: 'hello world'
message:
    description: The output message that the test module generates.
    type: str
    returned: always
    sample: 'goodbye'
"""


class _Document:
    def __init__(self):
        self._items = []
        self._sections = {}

    def add(self, item):
        self._items.append(item)
        if isinstance(item, _Section):
            self._sections[item.name] = item

    def section(self, name):
        try:
            return self._sections[name]
        except KeyError:
            s = _Section(name)
            self._sections[name] = s
            self._items.append(_Blank())  # spacing only
            self._items.append(s)
            return s

    def option(self, section, name):
        return self.section(section).option(name)

    def remove_section(self, name):
        s = self._sections.pop(name)
        self._items.remove(s)

    def render(self, indent="  "):
        for x in self._items:
            yield from x.render(indent)

    def stringify(self, indent="  "):
        return "".join(self.render(indent))

    def __eq__(self, other):
        return isinstance(other, _Document) and self._items == self._items


class _Section:
    def __init__(self, name):
        self.name = name
        self._options = {}
        self._items = []
        self._commented = False

    def add(self, item):
        self._items.append(item)
        if isinstance(item, _Option):
            self._options[item.name] = item

    def option(self, name):
        try:
            return self._options[name]
        except KeyError:
            o = _Option(name, "")
            self._options[name] = o
            self._items.append(o)
            return o

    @property
    def commented(self):
        return self._commented

    @commented.setter
    def commented(self, value):
        self._commented = value
        for option in self._options.values():
            option.commented = value

    def remove_option(self, name):
        o = self._options.pop(name)
        self._items.remove(o)

    def render(self, indent="  "):
        if self._commented:
            yield ";{}[{}]\n".format(indent, self.name)
        else:
            yield "{}[{}]\n".format(indent, self.name)
        for x in self._items:
            yield from x.render(indent)

    def __eq__(self, other):
        return isinstance(other, _Section) and self._items == other.items


class _Blank:
    def render(self, indent="  "):
        yield "\n"

    def __eq__(self, other):
        return isinstance(other, _Blank)


class _Comment:
    def __init__(self, text):
        self.text = text

    def render(self, indent="  "):
        yield self.text

    def __eq__(self, other):
        return isinstance(other, _Comment) and self.text == other.text


class _Option:
    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.commented = False

    def render(self, indent="  "):
        if self.commented:
            yield ";{}{}{} = {}\n".format(indent, indent, self.name, self.value)
        else:
            yield "{}{}{} = {}\n".format(indent, indent, self.name, self.value)

    def __eq__(self, other):
        return (
            isinstance(other, _Option)
            and self.name == other.name
            and self.value == other.value
            and self.commented == other.commented
        )


def _parse_conf(path):
    d = _Document()
    prev = d
    with open(path, "rt") as f:
        for line in f:
            sline = line.strip()
            if len(sline) == 0:
                d.add(_Blank())
            elif sline.startswith(("#", ";")):
                d.add(_Comment(line))
            elif sline.startswith("["):
                m = re.match(r"\[([^\]]+)\]", line)
                s = _Section(m.group(1))
                prev = s
                d.add(s)
            else:
                m = re.match(r"\s*(.+?)\s*=\s*(.+?)\s*", line)
                o = _Option(m.group(1), m.group(2))
                prev.add(o)
    return d


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        path=dict(type="str", required=True),
        section=dict(type="str", required=True),
        state=dict(
            type="str", choices=("present", "absent", "commented"), default="present"
        ),
        option=dict(type="str"),
        value=dict(type="str"),
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # changed is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
        changed=False,
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    path = module.params["path"]
    section = module.params["section"]
    state = module.params["state"]
    option = module.params["option"]
    value = module.params["value"]

    if state == "present" and (option is None or value is None):
        module.fail_json(
            msg="When state is 'present', option and value are required", **result
        )

    if state in ("absent", "commented") and option is not None and value is not None:
        module.fail_json(
            msg="When state is 'absent' or 'commented' and option is provided, value cannot be provided",
            **result,
        )

    conf = _parse_conf(path)
    orig = copy.deepcopy(conf)

    if state == "absent" and option is None:
        conf.remove_section(section)
    if state == "commented" and option is None:
        conf.section(section).commented = True

    if state == "absent" and option is not None:
        conf.section(section).remove_option(option)
    if state == "commented" and option is not None:
        conf.option(section, option).commented = True

    if state == "present":
        conf.section(section).option(option).value = value

    # use whatever logic you need to determine whether or not this module
    # made any modifications to your target
    # if module.params['new']:
    #    result['changed'] = True
    changed = conf != orig
    result["changed"] = changed

    if changed and not module.check_mode:
        with open(path, "w") as f:
            f.write(conf.stringify())

    # during the execution of the module, if there is an exception or a
    # conditional state that effectively causes a failure, run
    # AnsibleModule.fail_json() to pass in the message and the result
    # if module.params['name'] == 'fail me':
    #    module.fail_json(msg='You requested this to fail', **result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
