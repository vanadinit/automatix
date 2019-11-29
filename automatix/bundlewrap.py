from .command import Command


class BWCommand(Command):
    def _generate_python_vars(self):
        locale_vars = {}
        for key, value in self.systems.items():
            locale_vars[f'{key}_node'] = self.config["bw_repo"].get_node(value)
        locale_vars['vars'] = self.vars
        return locale_vars

    def _get_remote_hostname(self):
        node = self.config['bw_repo'].get_node(self.get_system())
        return node.hostname
