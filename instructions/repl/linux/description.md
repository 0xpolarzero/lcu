Control native apps or browsers on the user’s computer by reading or operating UI. Prefer purpose-built skills, connectors, APIs, or CLIs when available.

On your first call, or after a reset, execute exactly one of the API calls shown below, optionally assigning its result to a variable. Do not add other API calls, waits, or snapshots to that invocation.
The tool result will include documentation and, when selecting an app, its initial UI state. Read that result before continuing.
Use only APIs described in the tool instructions or returned documentation.

When you need an inventory of available apps and windows, get a snapshot of all enabled surfaces. Otherwise, use the relevant entry point below:

```javascript
await cua.getState();
```
