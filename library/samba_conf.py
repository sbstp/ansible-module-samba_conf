from __future__ import absolute_import, division, print_function
import copy
import re

from ansible.module_utils.basic import AnsibleModule


__metaclass__ = type

DOCUMENTATION = r"""
---
module: samba_conf
short_description: Modify samba configuration files easily without erasing comments.
version_added: "1.0.0" # TODO

description:
    - Modify samba configuration files easily, either by setting the value
    - of options, removing options, commenting options, removing sections or
    - commenting sections.
    -

options:
    path:
        description: Path to the Samba configuration file.
        required: true
        type: str
    state:
        description:
            - Desired state of the selected objects. When section is provided
            - but not option, the whole section is modified. When both section
            - and option are provided, only the option is modified. When section,
            - option and value are set this will set the given value to the given
            - option in the given section.
        choices:
            - present
            - absent
            - commented
        default: present
        type: str
    section:
        description: Name of the section to modify
        required: true
        type: str
    option:
        description: Name of the option to modify
        type: str
    value:
        description: Value of the selected option to modify
        type: str
# Specify this value according to your collection
# in format of namespace.collection.doc_fragment_name
# extends_documentation_fragment:
#     - my_namespace.my_collection.my_doc_fragment_name

author:
    - Simon Bernier St-Pierre (@sbstp)
"""

EXAMPLES = r"""
# Modify option
- name: Modify global workgroup
  sbstp.ansible.samba_conf:
    path: /etc/samba/smb.comf
    section: global
    option: workgroup
    value: ACME_INC

# Modify many options
- name: Modify multiple options
  sbstp.ansible.samba_conf:
    path: /etc/samba/smb.comf
    section: tank
    option: "{{ item.option }}"
    value: "{{ item.value }}"
  with_items:
    - option: path
      value: /tank/data
    - option: browseable
      value: "yes"

# Remove section
- name: Remove print$ Samba section
  sbstp.ansible.samba_conf:
    path: /etc/samba/smb.comf
    section: "print$"
    state: absent

# Comment section
- name: Comment print$ Samba section
  sbstp.ansible.samba_conf:
    path: /etc/samba/smb.comf
    section: "print$"
    state: commented
"""

RETURN = r"""
changed:
  description: Whether any changes were made.
  type: bool
"""


class _ParseError(Exception):
    def __init__(self, message, line, lineno) -> None:
        super().__init__()
        self.message = message
        self.line = line.rstrip()
        self.lineno = lineno + 1

    def __str__(self):
        return "{} at line {}: {!r}".format(self.message, self.lineno, self.line)


class _Document:
    def __init__(self):
        self._items = []
        self._sections = {}

    def add(self, item):
        self._items.append(item)
        if isinstance(item, _Section):
            self._sections[item.name] = item

    def section(self, name, create=True):
        try:
            return self._sections[name]
        except KeyError:
            if not create:
                raise
            s = _Section(name)
            self._sections[name] = s
            self._items.append(_Blank())  # spacing only
            self._items.append(s)
            return s

    def option(self, section, name, create=True):
        return self.section(section, create=create).option(name, create=create)

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

    def option(self, name, create=True):
        try:
            return self._options[name]
        except KeyError:
            if not create:
                raise
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


def _parse_conf(text):
    d = _Document()
    prev = d
    for lineno, line in enumerate(text.splitlines()):
        sline = line.strip()
        if len(sline) == 0:
            d.add(_Blank())
        elif sline.startswith(("#", ";")):
            d.add(_Comment(line))
        elif sline.startswith("["):
            m = re.match(r"^\s*\[([^\[\]]+)\]\s*$", line)
            if m is None:
                raise _ParseError("Invalid share definition", line, lineno)
            s = _Section(m.group(1))
            prev = s
            d.add(s)
        else:
            m = re.match(r"^\s*(.+?)\s*=\s*(.*?)\s*$", line)
            if m is None:
                raise _ParseError("Invalid syntax", line, lineno)
            o = _Option(m.group(1), m.group(2))
            prev.add(o)
    return d


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        path=dict(type="str", required=True),
        section=dict(type="str", required=True),
        state=dict(type="str", choices=("present", "absent", "commented"), default="present"),
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
        module.fail_json(msg="When state is 'present', option and value are required", **result)

    if state in ("absent", "commented") and option is not None and value is not None:
        module.fail_json(
            msg="When state is 'absent' or 'commented' and option is provided, value cannot be provided",
            **result,
        )

    try:
        with open(path, "rt") as f:
            conf = _parse_conf(f.read())
    except _ParseError as exc:
        # during the execution of the module, if there is an exception or a
        # conditional state that effectively causes a failure, run
        # AnsibleModule.fail_json() to pass in the message and the result
        module.fail_json(
            msg=str(exc),
            lineno=exc.lineno,
        )
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
    changed = conf != orig
    result["changed"] = changed

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment
    if changed and not module.check_mode:
        with open(path, "w") as f:
            f.write(conf.stringify())

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
