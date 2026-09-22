# Linux computer use

Use the initialized `cua` API through the `js` MCP tool. JavaScript bindings persist until `js_reset`. Use only the documented API. Prefer a task-specific connector or API when one is available.

## Select a window

Start with `await cua.getState()` or `await cua.listWindows()`. Both display their results. Select the requested app by its title and exact window ID, including when it has several windows:

```javascript
let app = await cua.getApp({ windowId: 123 });
```

Use an ID from the actual inventory. Selection also displays the initial accessibility state. If the app is not open, `await cua.computer.launch_app({ app: appId })` accepts an app ID from `cua.listApps()`. Refresh the inventory after launching. `getApp` never launches Linux apps.

## API

```typescript
type Point = [x: number, y: number];
type Observation = { emit?: boolean; disableDiffing?: boolean };
type Direction = "up" | "down" | "left" | "right" | "u" | "d" | "l" | "r";
interface App {
  getAXState(options?: Observation): Promise<string>;
  getScreenshot(options?: { emit?: boolean }): Promise<Uint8Array>;
  getAXStateAndScreenshot(options?: Observation): Promise<{state: string; screenshot?: Uint8Array}>;
  click(target: number | string | Point, options?: {mouseButton?: "left" | "right" | "middle" | "l" | "r" | "m"; clickCount?: number}): Promise<void>;
  drag(from: Point, to: Point): Promise<void>;
  scroll(target: number | string | Point, direction: Direction, distance?: {pixels: number}): Promise<void>;
  pressKey(key: string): Promise<void>;
  typeText(text: string): Promise<void>;
  paste(text: string, options?: {format?: "text"}): Promise<void>;
  performSecondaryAction(element: number | string, action: string): Promise<void>;
}
declare const cua: {
  getState(options?: Observation): Promise<{apps: unknown[]; browsers: []; errors?: string[]}>;
  listApps(options?: Observation): Promise<unknown[]>;
  listWindows(options?: Observation): Promise<{id: number; app: string; title?: string}[]>;
  getApp(target: {windowId: number}): Promise<App>;
  rewriteDocumentation(): Promise<void>;
  computer: {target: "linux"; launch_app(input: {app: string}): Promise<void>};
};
```

## Observe, act, verify

Linux returns a full accessibility tree with its source. Use current element IDs and the actions exposed in that tree. `at_spi` elements support the listed actions. `x11` fallback elements only describe the window: use a screenshot and coordinates to act on them.

Coordinates are relative to the selected window. Input stays bound to that window and ordinarily does not activate it or move the desktop pointer. The application itself can activate a window or grab the pointer during interactions.

Batch deterministic actions, then call `await app.getAXState()` before deciding the next action. Use the new tree to choose element IDs. Screenshots help when the tree omits visible information. Reacquire the binding when the target window changes. There is no need to sleep before observations: the runtime already settles actions.

`pressKey` uses xdotool key names, such as `Return`, `Tab`, `ctrl+a`, and `Shift+Left`. `typeText` and `paste` use native text input; paste accepts text only. `scroll` accepts a positive pixel distance, such as `{ pixels: 500 }`, or the native default when omitted. Element clicks accept a single left or right click; use coordinates for other click options. `setValue` and `selectText` are unavailable and throw. Edit with click, key presses, and text input instead.

`performSecondaryAction` requires an action explicitly exposed for that element. Do not guess action names. Verify the requested outcome in the returned UI state; a successful input call alone does not prove completion.

## Output and recovery

Observation and inventory methods display their own results. Do not wrap them in another output call. `{ emit: false }` suppresses the result when reading it programmatically; first-use documentation is still shown. For other data, use `nodeRepl.write(value)`. For an image, use `await nodeRepl.emitImage(bytes)` or `{ bytes, mimeType }`.

After context compaction, run `await cua.rewriteDocumentation()`. Use `js_reset` when the persistent session needs resetting; this clears bindings without closing applications. Re-observe before further input. Dedicated browser-provider APIs are absent; browser windows can still be controlled through the same Linux desktop API.
