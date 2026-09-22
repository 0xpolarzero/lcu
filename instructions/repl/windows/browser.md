Use the first matching browser control option from the user's request:

For a tab @-mention (`mention=tab-v1`):
Pass the complete `plugin://...` URL to get the referenced tab.

```javascript
let tab = await cua.getTab({ mention: tabMentionUrl });
```

For an existing tab identified by URL in browser context (including the current IAB tab):

```javascript
let tab = await cua.getTab({ url }, { browser: browserId });
```

Known tab ID (`tabId` or `providerTabId`) and browser (name or browser @-mention):

```javascript
let tab = await cua.getTab(tabId, { browser: browserId });
```

To open a URL in the in-app browser (`@Browser`):

```javascript
let tab = await cua.createBrowserTab("iab", url, { visible: boolean });
```

To open a URL in another named browser: pass its name directly; do not call `getBrowser` first.

```javascript
let tab = await cua.createBrowserTab(browserName, url, browserOptions);
```

Known URL, only when the user has not specified a browser by name or @-mention:

```javascript
let browser = await cua.getBrowser({ url });
```

Browser IDs and options:

- `"iab"` (in-app browser): in `createBrowserTab`, use `visible: true` to show the browser; `false` to keep it hidden.
- `"chrome"` (@Chrome), `"edge"` (@Edge): pass a short, emoji-prefixed `sessionName` (e.g. `"🔎 Task"`) to `createBrowserTab` when starting a task.
