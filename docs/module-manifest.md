# Module Manifest

The module manifest (`manifest.toml`) contains metadata which describes your module, and provides information to Breadcord. It is a [TOML document](https://toml.io/) located in the root directory of your module.

A valid module manifest must contain a `manifest_version` key which helps Breadcord identify your module. Currently, this should be set to a value of `1`. This is followed by a number of [module fields](#fields) under the `[module]` table.

## Example
```toml
manifest_version = 1

[module]
name = "Example Module"
id = "example_module"
description = "This is an example of a Breadcord module manifest."
version = "0.1.0"
license = "GNU GPLv3"
authors = ["Alice", "Bob"]
requirements = ["aiohttp", "pillow>=9.0.0", "numpy==1.24.*"]
permissions = ["read_messages", "send_messages"]
```

## Fields
> - [name](#name)
> - [id](#id)
> - [description](#description)
> - [version](#version)
> - [license](#license)
> - [authors](#authors)
> - [requirements](#requirements)
> - [permissions](#permissions)

### `name`[<sup>🔸</sup>](#required "This field is required")
The name of your module in human-readable text.

**Type:** String  
**Length:** 1-64 characters (inclusive)  
**Examples:** `"Example Module"`, `"My ✨special✨ module!"`

### `id`[<sup>🔸</sup>](#required "This field is required")
A unique identifier for your module, which will be used to identify and select it both by Breadcord and the end user.

!!! warning

    Before choosing an ID, please make sure it's not already in use by another published module!

**Type:** String (lowercase letters a-z and underscores only)  
**Length:** 1-32 characters (inclusive)  
**Examples:** `"example_module"`, `"my_special_module"`

### `description`
Human-readable text describing the module.

**Type:** String  
**Length:** 1-128 characters (inclusive)  
**Example:** `"This is an example of a Breadcord module manifest."`

### `version`[<sup>🔸</sup>](#required "This field is required")
The module's current version.

**Type:** String using the [Python version specifier](https://packaging.pypa.io/en/stable/version.html#packaging.version.Version) (following [PEP 440](https://peps.python.org/pep-0440/)) format  
**Examples:** `"0.1.0"`, `"1.0"`, `"1.2.3rc1"`

### `license`
Short name of the license the module is under (e.g. `GNU GPLv3`). Tips for choosing a licence can be found [here](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository#choosing-the-right-license).

**Type:** String  
**Length:** 1-16 characters (inclusive)  
**Examples:** `"GNU GPLv3"`, `"MIT"`, `"WTFPL"`

### `authors`
A list of module author names. Take credit for your work!

**Type:** List of strings  
**Length:** 1-32 characters (inclusive) per element  
**Example:** `["Alice", "Bob"]`

### `requirements`
A list of requirements to be automatically installed using [`pip`](https://pip.pypa.io/) when the module is being loaded.

**Type:** List of strings using the [pip requirement specifier](https://pip.pypa.io/en/stable/reference/requirement-specifiers/) format  
**Example:** `["aiohttp", "pillow>=9.0.0", "numpy==1.24.*"]`

!!! warning

    Keep in mind that your requirements could conflict with requirements from another module, so keep your requirements broad where you can!

### `permissions`
A list of guild permissions the module requires to function. These will be shown to the user upon installation.

**Type:** List of strings as enumerated by [discord.Permissions](https://discordpy.readthedocs.io/en/latest/api.html#discord.Permissions)  
**Example:** `["read_messages", "send_messages"]`

---

<h6 id="required">Required fields are marked with 🔸</h6>
