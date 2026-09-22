If the user specifies an app to use, get the app by its exact open window ID from `cua.getState()` or `cua.listWindows()`. If an app has multiple windows, use their titles to choose the requested one. Do not choose the first window without checking it.

```javascript
let app = await cua.getApp({ windowId: 123 });
```
