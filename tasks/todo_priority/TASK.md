Add task priorities to the `todo` package.

1. `Task` gets a `priority` field: `low`, `normal` or `high`, default `normal`.
2. `add <title> --priority low|normal|high`. The option is optional and defaults to `normal`. An invalid value exits with status 2.
3. `list --sort priority` shows high, then normal, then low, and by ascending id within a priority. Without `--sort`, keep ordering by id.
4. `list` lines keep the current format, but non-normal tasks end with the priority in parentheses, for example `1 [ ] Buy milk (high)`.
5. The file format becomes `{"version": 2, "tasks": [...]}`. `Store.load` must still read the old format (a bare JSON list), treating those tasks as `normal`. `Store.save` always writes version 2. Any other version raises `ValueError`.

`done` must keep working and must not change a task's priority.
