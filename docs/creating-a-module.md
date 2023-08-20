# Creating a Module

To start developing your own module, you first need to create the required files inside your `modules/` directory. These files are as follows:

```
my_module/
├─ __init__.py
├─ manifest.toml
└─ settings_schema.toml  (optional)
```

### \_\_init\_\_.py
This is the entrypoint into your module. When your module is loaded, Breadcord will try to import from this file.
<!--
`__init__.py` will eventually also be optional, for libraries.
https://discord.com/channels/1042824621646413854/1043976078630342767/1103088521566228490
-->

### manifest.toml
This contains metadata which describes your module to Breadcord. See the [Module Manifest](module-manifest.md) page for more information.

### settings_schema.toml
This defines the settings which your module uses, to be added to the `settings.toml` file. This file is optional and can be omitted if your module does not need any settings.

