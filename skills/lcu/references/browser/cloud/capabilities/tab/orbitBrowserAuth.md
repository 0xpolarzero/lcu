# Tab Capability: browserAuth
Collects user-provided credentials for a validated login form and fills them into this tab without returning the values to the caller. Include `submit` only when the page requires an explicit submission action. Omit it for forms that auto-submit during credential entry.

## Browser Authentication
Read this guidance before beginning sign-in. Handle account and method
choices, identifier-only steps, and one-time codes through chat or ordinary browser
interactions. `browserAuth.request(...)` is the secure handoff for passwords and
other reusable secrets. Browser-client validates, fills, and submits those values
without returning them to you.

### Non-Negotiable Rules
- Never ask the user to paste passwords, security answers, recovery codes, or
  other reusable secrets into chat.
- Never enter, read, inspect, log, print, or reconstruct reusable secrets with
  Playwright, vision, tool output, or any other model-visible surface.
- Use secure credential requests for reusable secrets. Include an unknown
  username, email address, or phone number when the same form also requires a
  password. Never include one-time codes or sign-in `options`; handle them
  through chat or ordinary browser interactions instead.
- Never emit a legacy `<browser_auth_request>` block or use a legacy form-fill
  path.
- CAPTCHAs are outside `browserAuth`. Never use this capability for one; follow
  the CAPTCHA guidance in the main Browser skill.
- Never include secrets, cookies, full URLs, query strings, JavaScript,
  DOM snippets, or other page content in a browser-auth request. Browser-client
  supplies the request message; do not provide one. Credential-field and
  sign-in option labels must describe only controls actually visible on the
  current page.
- If `browserAuth` returns `unavailable`, stop automated credential entry. If
  this browser's guidance permits manual takeover, offer its documented
  handoff. Otherwise, politely say that this browser cannot help the user log
  in to the site; do not explain why. For this refusal, do not add login steps
  unless the user explicitly asks how to sign in themselves. Never tell the
  user to sign in and come back; signing in in their browser does not sign in
  this browser. Do not fall back to chat or direct entry for reusable secrets.
- If login blocks only part of a broader task, keep and return any useful public
  work already completed.

### Authentication Lifecycle
1. Before the first authentication interaction, retain the target site's origin
   or a canonical signed-in URL for later verification, for example with
   `const targetOrigin = new URL(await tab.url()).origin`.
2. Inspect the visible page. Use only methods the page actually offers, such as
   phone or SMS OTP, email or Gmail OTP, Google sign-in, username and password,
   passkey, or device approval. Honor the user's stated identity and method
   preference. Reuse relevant memory and available account context for their
   username, email, or phone number; do not ask them to repeat known information.
   Autofill known identifiers through ordinary browser interactions. On an
   identifier-only step, ask for an unknown identifier in chat. If the current
   form asks for both an unknown identifier and a password, collect both in one
   `browserAuth.request(...)` instead of asking separately in chat.
   When the user supplies an identifier for the current sign-in, that is explicit
   authorization to fill it; do not ask for another confirmation before entering
   it. If the intended identity is ambiguous, ask a concise question in chat.
   On an account chooser, when one already signed-in account is offered, select
   it directly unless it conflicts with the user's stated identity or preference.
   Do not ask whether they want to use a different account. With multiple
   accounts, select a clear match to the intended identity; ask in chat if the
   choice remains ambiguous.
   Without a stated method preference, choose the offered path that needs the
   least user intervention: prefer email OTP through a matching connected
   mailbox, then Google sign-in with an already signed-in account, then phone
   OTP. Make these selections directly. Ask in chat only when the intended
   method remains ambiguous; do not use secure elicitation for method choices.
   You may open Google sign-in to check for an already signed-in account; if it
   instead requires a fresh Google login, return to the service's other sign-in
   options rather than defaulting to Google.
3. Follow the selected method through the visible page. Handle identifiers as
   described above and enter one-time sign-in codes through ordinary browser
   interactions. Retrieve an email OTP only from the connected mailbox matching
   the chosen identity and
   current sign-in attempt. If that mailbox is unavailable, ask for the code in
   chat. Ask for phone OTPs in chat when needed. Use a code only for that attempt;
   do not echo or save it.
   For Google verification, select an existing phone OTP method first, then
   device approval. Do not ask the user to choose when that selection is clear.
   Use `browserAuth.request(...)` only when reusable secrets are needed, or for
   the QR approval flow below. Include an unknown identifier with the password
   when both are requested on the same form; omit identifiers already filled.
   If the flow would create an account, confirm permission in chat, naming the
   identity that would be used and offering to use another existing account.
   Signing in or using a service does not itself authorize registration. Honor
   explicit signup authorization already given.
   If the website displays a QR code for approval on another device, call
   `browserAuth.request({ origin: new URL(await tab.url()).origin, fields: [], qr_code: true })`.
   Browser-client securely captures and decodes the visible QR code. Never
   inspect, print, copy, or reconstruct its destination URL yourself. The only
   exception is a trusted native-mobile handoff error that explicitly provides
   a validated HTTPS sign-in URL: show the user that exact supplied URL, ask
   them to open it and report back when finished, and wait for their reply.
   Never expose another QR payload or derive a URL the error did not supply.
   If two-step verification or device approval displays a number-matching
   challenge, tell the user the exact non-secret number or matching detail to
   select on their device, for example, "Tap 37 on your phone."
   If the matching detail is an emoji, icon, or image, describe that exact
   visual cue, for example, "Tap the 🥶 emoji on your phone." Never invent a
   number or translate an image into a numeric code. Do not request
   manual browser takeover when approval on another device is sufficient. After
   the user confirms, inspect the current page and continue authentication.
   Repeat the account and method selection rules at each new authentication or
   recovery decision point. If the selected method fails, inspect the
   website-surfaced error before requesting credentials again. For an incorrect
   username, password, or verification code, report the error and, if this browser's guidance
   permits manual takeover, offer its documented handoff. Otherwise, let the
   user choose whether to retry or use a visible alternative. Never switch
   methods without the user's choice. If the site explicitly blocks sign-in or
   reports a generic failure such as "An error occurred" or "Something went
   wrong," stop after the first occurrence and explain that the website might
   be blocking sign-in. When using Cloud Browser, share the Help Center article
   in its guidance.
4. After every authentication transition, call
   `nodeRepl.write(await tab.dom_cua.get_visible_dom())` to inspect the rendered
   interactive structure across nested and cross-origin frames. Check for a
   CAPTCHA, error, next authentication step, or success. If the inspection
   appears incomplete, use a frame-aware inspection and interaction path; do not
   continue, assume success, or dismiss an overlay.
5. When authentication appears complete, verify the target site with fresh
   visible evidence. Treat a closed auth popup, blank page, spinner, missing tab,
   stale tab, or timeout as an unknown result, not a failed login and not proof
   of success.
6. If the target page fails to load after authentication, immediately create a
   new agent tab and navigate it to the retained target origin or canonical
   signed-in URL:

   ```js
   const verificationTab = await browser.tabs.new();
   await verificationTab.goto(targetOrigin);
   nodeRepl.write(await verificationTab.dom_cua.get_visible_dom());
   ```

   Inspect that fresh page. Authentication may already have succeeded and its
   cookies may be available even when the original tab or popup is stuck. Make
   this fresh-tab check the first recovery action; do not poll the stale tab,
   enumerate tabs, or reconnect first.
7. Report success only when the fresh target-domain page shows a positive
   signed-in signal. If the fresh page shows a login or verification screen,
   continue the authentication workflow from that page. If browser access still
   fails, report the state as unknown; never ask the user to check or operate
   this browser.

### Prepare A Credential Request
1. Inspect the live sign-in form with the cheapest targeted browser-side check
   that identifies the currently visible credential fields and submit behavior,
   such as visible-DOM inspection or narrowly scoped locator checks.
   Inspect what has already rendered; do not wait for page-load completion or
   repeatedly request full DOM snapshots.
2. Include only inputs that are visible and enabled on the current page: reusable
   secrets and any unknown identifier requested alongside a password. Omit
   identifiers already filled. One-time codes belong in ordinary browser
   interactions, never in this secure request.
   Issue exactly one request at a time for the current sign-in page. For
   multi-step sign-in, inspect the new page and make a separate request after
   each navigation.
3. Start with `tab.playwright.domSnapshot()` to identify iframe hierarchy and
   owner attributes. `tab.dom_cua.get_visible_dom()` omits frame ownership.
   If a field, option, or submit is inside an iframe, use its `frameLocator(...)`;
   use `frameLocator("iframe")` only when it resolves uniquely. Choose stable
   selectors that each resolve to exactly one field. Prefer semantic attributes
   such as `name`, `type`, and `autocomplete`. Avoid random-looking generated
   IDs when a stable semantic selector is available. Do not infer attributes
   that were not inspected.
4. Set each field's `type` to its actual non-empty HTML input type. For
   example, a password input may be `password`, and a security answer input
   may be `text`.
   Pass the inspected `autocomplete` value when the page exposes one.
   Set `label` to a short noun phrase describing only what the user should
   enter. Prefer concise wording visible on the page; otherwise use a natural
   label such as `Password`, `Security answer`, or `Recovery code`.
   Do not include instructions, explanations, required markers, account-specific
   values, or complete sentences.
5. Use only the current canonical origin, with scheme, host, and port but no
   path, query, or fragment.
6. Omit `submit` when filling the credential fields causes the form to
   auto-submit. Otherwise, use `click` only for a stable selector that resolves
   to exactly one visible enabled submit control distinct from the credential
   fields. If Enter on the final credential field submits the form, including
   when the submit button is disabled until input is present, use `press_enter`
   with that exact field selector instead of a broad or generic button selector.

If a visible textbox may be inside a component or shadow root, inspect its
`id`, `name`, and `type` attributes through a browser-side role locator, then
verify the resulting exact CSS selector with browser-side Playwright locator
count, visibility, and enabled checks. An accessible name reported by a role
locator is not proof that an `aria-label` attribute exists. Never infer an
`aria-label` selector; use one only when the inspected attribute is actually
present. Do not treat `document.querySelectorAll(...)` returning zero as
authoritative for a shadow-root textbox.

Use only the existing browser-side surface for sign-in inspection. Do not run
shell commands, standalone or local Playwright, package installs, browser
runtime installs, or reconnect attempts to inspect the site. Reuse existing
browser and tab handles for browser-side checks.

Browser-client is the source of truth for whether the request is safe to show
to the user. After a targeted inspection, call `browserAuth.request(...)` with
the best candidate selectors without repeatedly re-verifying them or stopping
merely because model-side proof is incomplete. If it returns `locator_invalid`,
re-inspect and correct the request instead of guessing or treating model-side
checks as authoritative.

If the targeted inspection itself fails, make at most one additional
browser-side tool call: a lighter targeted check against already rendered
state. If it still cannot identify candidate selectors for every required
visible enabled field, stop inspection and, if this browser's guidance permits
manual takeover, offer its documented handoff; otherwise, report the blockage.
Do not issue further browser-side navigation, DOM, locator, reconnect, shell,
or runtime-install calls for that sign-in attempt.

### Request Credentials
Get the advertised capability and issue a request containing only non-secret
metadata and selectors. For a combined form with an unknown username and password:

```js
const browserAuth = await tab.capabilities.get("browserAuth");
const browserAuthUrl = await tab.url();
if (!browserAuthUrl) {
  throw new Error("Cannot determine the current tab URL for browser auth.");
}

const usernameField = tab.playwright.locator('input[name="username"]');
const passwordField = tab.playwright.locator('input[type="password"]');
const submitButton = tab.playwright.locator('button[type="submit"]');

const browserAuthResult = await browserAuth.request({
  origin: new URL(browserAuthUrl).origin,
  fields: [
    {
      id: "username",
      label: "Username",
      type: "text",
      autocomplete: "username",
      required: true,
      selector: usernameField,
    },
    {
      id: "password",
      label: "Password",
      type: "password",
      autocomplete: "current-password",
      required: true,
      selector: passwordField,
    },
  ],
  submit: {
    selector: submitButton,
    action: "click",
  },
});
nodeRepl.write(browserAuthResult);
```

The example selectors are illustrative. Always inspect the current page and use
selectors that match its actual fields. If these controls are inside an iframe:

```js
const frame = tab.playwright.frameLocator("iframe#auth");
const field = frame.locator('input[type="password"]');
const submit = frame.locator('button[type="submit"]');
```

Omit `submit` when the form auto-submits during credential entry.

### Handle The Credential Request Result
- `submitted` means credential entry completed and any configured submit action
  ran; it does not prove that sign-in succeeded. Resume the Authentication
  Lifecycle at its transition-inspection step.
- `locator_invalid`, `page_changed`, or `origin_changed` means the saved request
  is stale or unsafe. If authentication still blocks the task, re-inspect the
  current page and issue a corrected fresh request. If browser auth reports
  `not_user_visible`, retry the exact same credential request without that field.
- `expired` is a legacy result from an older browser runtime. Re-inspect before
  issuing a fresh request.
- `declined` with `reason: "user_took_over"` means the user took manual control
  of the cloud browser; their actions and final authentication state are
  unknown. Inspect the final page state with fresh visible DOM, then continue the
  Authentication Lifecycle from its transition-inspection step. Do not inspect
  or act on any intermediate state from the manual sign-in.
- `declined` without that reason or `cancelled` means the user chose not to
  continue. Respect that choice and do not retry unless the user asks.
- `unavailable` must never trigger a fallback to chat or direct entry of
  reusable secrets. Follow the refusal guidance above.
- `submission_failed` must never trigger a fallback to chat or direct entry of
  reusable secrets. Inspect the current page for a non-secret website error and
  report it only if the website visibly shows it. Otherwise, follow the refusal
  guidance above.
- The result never contains credential values. Never try to print or
  reconstruct them.

## API Reference
```ts
const capability = await tab.capabilities.get("browserAuth");

type BrowserAuthRequestOptions = Omit<BrowserAuthHandoffOptions, "fields" | "options" | "submit"> & { fields: Array<BrowserAuthRequestField>; options?: Array<BrowserAuthRequestOption>; submit?: BrowserAuthRequestSubmit };

type BrowserAuthHandoffOptions = z.infer<typeof BrowserAuthHandoffOptionsSchema>;

type BrowserAuthRequestField = Omit<BrowserAuthField, "selector"> & { selector: BrowserAuthSelector };

type BrowserAuthRequestOption = Omit<BrowserAuthOption, "selector"> & { selector?: BrowserAuthSelector };

type BrowserAuthRequestSubmit = Omit<BrowserAuthSubmit, "selector"> & { selector: BrowserAuthSelector };

type BrowserAuthField = z.infer<typeof BrowserAuthFieldSchema>;

type BrowserAuthSelector = string | PlaywrightLocator;

type BrowserAuthOption = z.infer<typeof BrowserAuthOptionSchema>;

type BrowserAuthSubmit = z.infer<typeof BrowserAuthSubmitSchema>;

interface BrowserAuthTabCapability {
  request(options: BrowserAuthRequestOptions): Promise<{ locator_error?: { field_id: string; reason: "not_user_visible" }; reason?: "user_took_over"; selected_option?: string; status: "submitted" | "declined" | "cancelled" | "unavailable" | "expired" | "origin_changed" | "page_changed" | "locator_invalid" | "submission_failed" }>; // Request user-provided credentials for a validated login form. When `submit` is omitted, a `submitted` result means the credential fields were filled successfully; inspect the resulting page to confirm that the form auto-submitted and sign-in advanced.
}
```
