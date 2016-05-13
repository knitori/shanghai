
import ast
import _ast
import importlib.util
import os
import sys
from types import ModuleType


class PluginException(Exception):
    def __init__(self, message, filename, lineno, offset=None):
        with open(filename, 'r', encoding='utf-8') as f:
            lines = list(f)
            line = lines[lineno-1].strip()
        msg = '\n'
        msg += '  File {!r}, line {}\n'.format(filename, lineno)
        msg += '    {}\n'.format(line)
        if offset is not None:
            msg += '    {:>{}}\n'.format('^', offset+1)
        msg += message
        super().__init__(msg)


class PluginRegistry(ModuleType):
    plugins = {}

    def __getattr__(self, name):
        if name in self.__class__.plugins:
            return self.__class__.plugins[name].module
        raise AttributeError('No such plugin {!r}'.format(name))


class Plugin:

    def __init__(self, name, version, description, depends, file, module):
        self.name = name
        self.version = version
        self.description = description
        self.depends = depends
        self.required_by = {}
        self.file = file
        self.module = module

    def __del__(self):
        print('Plugin {} died'.format(self.name))

    def __repr__(self):
        return ('{s.__class__.__name__}('
                'name={s.name!r}, '
                'version={s.version!r}, '
                'module={s.module!r})'
                .format(s=self))

    @staticmethod
    def find_plugin(name):
        # simple way for now
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, 'plugins', '{}.py'.format(name))

    @classmethod
    def load_plugin(cls, name):
        return cls._load_plugin(name, [])

    @classmethod
    def _load_plugin(cls, plugin_name, dep_path):
        """Load plugin and all its dependencies.

        :param str plugin_name: Name of the plugin
        :param list dep_path: Dependency path
        :return: Plugin
        """

        if plugin_name in PluginRegistry.plugins:
            return PluginRegistry.plugins[plugin_name]
        plugin_file = cls.find_plugin(plugin_name)
        with open(plugin_file, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        data = {
            'depends': [],
        }

        # before we load the plugin, we search for __name__ etc. assignments
        # in the module using the ast module. This only parses, but doesn't
        # execute.
        for stmt in tree.body:
            if not isinstance(stmt, _ast.Assign):
                continue
            if len(stmt.targets) != 1:
                continue
            if not isinstance(stmt.targets[0], _ast.Name):
                continue
            target = stmt.targets[0].id
            if target not in ('__name__', '__description__', '__version__',
                              '__depends__'):
                continue
            if not isinstance(stmt.value, (_ast.Str, _ast.List, _ast.Tuple)):
                raise PluginException('Unsupported type {}'.format(stmt.value),
                                      plugin_file, stmt.value.lineno,
                                      stmt.value.col_offset)
            target = target.strip('_')
            value = None
            if isinstance(stmt.value, _ast.Str):
                value = stmt.value.s
            elif isinstance(stmt.value, (_ast.List, _ast.Tuple)):
                value = []
                for element in stmt.value.elts:
                    if isinstance(element, _ast.Str):
                        value.append(element.s)
                    else:
                        raise PluginException(
                            'Unsupported type {}'.format(element),
                            plugin_file, element.lineno, element.col_offset)
            data[target] = value

        assert 'name' in data and 'version' in data and 'description' in data
        # `__name__` is a "displayable" name while
        # `plugin_name` is the import name.

        # before loading this plugin, we have to load the dependencies.
        deps = {}
        for dep_name in data['depends']:
            if dep_name in dep_path:
                path = dep_path + [plugin_name, dep_name]
                path_msg = ' -> '.join(repr(dep) for dep in path)
                raise RuntimeError('Dependency cycle detected:\n'
                                   '  {}'.format(path_msg))
            dep = cls._load_plugin(dep_name, dep_path + [plugin_name])
            deps[dep_name] = dep

        # wrap things up
        data['depends'] = deps
        data['file'] = plugin_file
        module_path = 'shanghai.ext.{}'.format(plugin_name)

        # python3.5+, load by full file path.
        spec = importlib.util.spec_from_file_location(
            module_path, plugin_file)
        data['module'] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(data['module'])

        sys.modules[module_path] = data['module']

        plugin = cls(**data)
        PluginRegistry.plugins[plugin_name] = plugin
        sys.modules[module_path].__plugin__ = plugin
        for dep_name, dep in plugin.depends.items():
            dep.required_by[plugin_name] = plugin
        print('Loaded', plugin_name)
        return plugin

    @classmethod
    def unload_plugin(cls, plugin_name):
        return cls._unload_plugin(plugin_name)

    @classmethod
    def _unload_plugin(cls, plugin_name):
        if plugin_name not in PluginRegistry.plugins:
            raise KeyError('No such plugin {!r}'.format(plugin_name))
        plugin = PluginRegistry.plugins[plugin_name]

        required_plugins = []
        # we need to unload plugins, that require this one first.
        for req_name in plugin.required_by:
            required_plugins += cls._unload_plugin(req_name)

        module_path = 'shanghai.ext.{}'.format(plugin_name)
        if module_path in sys.modules:
            del sys.modules[module_path]
        del PluginRegistry.plugins[plugin_name]
        print('Unloaded', plugin_name)
        return [plugin_name] + required_plugins

    @classmethod
    def reload_plugin(cls, plugin_name):
        unloaded = []
        try:
            unloaded = cls.unload_plugin(plugin_name)
        except KeyError:
            pass
        for pname in unloaded:
            cls.load_plugin(pname)


sys.modules['shanghai.ext'] = PluginRegistry('shanghai.ext')
sys.modules['shanghai.ext'].__dict__.update({
    '__file__': os.path.abspath(__file__),
    '__path__': os.path.dirname(os.path.abspath(__file__)),
})
