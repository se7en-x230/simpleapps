tomlc99 by C. K. Tan, https://github.com/cktan/tomlc99
Retrieved 2026-10-08 from upstream master: toml.c, toml.h, LICENSE.
MIT license retained in LICENSE.tomlc99.
One local compatibility change: the local dot pointer in toml_rtod_ex is const
char*, matching the const input string with current C compiler headers.
The vendored copies make the local build independent of network availability.
