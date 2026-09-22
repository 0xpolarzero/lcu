Use the first matching browser control option from the user's request:

For an existing tab identified by URL in browser context:

```javascript
let tab = await cua.getTab({ url }, { browser: "cdp" });
```

Known tab ID (`tabId` or `providerTabId`):

```javascript
let tab = await cua.getTab(tabId, { browser: "cdp" });
```

To open a URL when the user specifies a browser by name or @-mention: use the cloud browser ID `"cdp"` directly; do not call `getBrowser` first.

```javascript
let tab = await cua.createBrowserTab("cdp", url);
```

Known URL, only when the user has not specified a browser by name or @-mention:

```javascript
let browser = await cua.getBrowser({ url });
```

Browser IDs:

- `"cdp"`: the cloud browser.
