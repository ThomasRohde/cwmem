# Textual: technical research report

Version note: this report uses the locally installed `textual 8.1.0` package for line-accurate source citations, and supplements that with upstream repository metadata from [Textualize/textual](https://github.com/Textualize/textual), whose `main` branch currently advertises `8.1.1` in `pyproject.toml`.[^1][^2]

## Executive Summary

Textual is a production-stable, typed, MIT-licensed Python framework for building terminal-first user interfaces on Python 3.9+, maintained by Will McGugan / Textualize and documented at `https://textual.textualize.io/`.[^1] Its core architecture is a DOM-style tree in which `App` is the root, `Screen` is a specialized `Widget`, and every DOM participant ultimately inherits `MessagePump`, which supplies async message dispatch, timers, mount lifecycle, and callback scheduling.[^3][^4] The framework feels "web-like" because it combines generator-based composition, Textual CSS, selectors, reactive state, screen stacks, command providers, and background workers, while still letting simple apps stay mostly synchronous at the call site even though the runtime is async internally.[^5][^6][^7] Textual also has a browser/publication path: its packaged metadata documents `textual serve` and Textual Web, and the installed code includes a `WebDriver` that emits structured data/meta packets and supports browser-oriented operations such as opening URLs and delivering files to end users.[^8][^9]

## Architecture / system overview

```text
┌──────────────────────────────────────────────────────────────┐
│                        User App Code                         │
│      App subclass + compose() + CSS / CSS_PATH + actions    │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                           App                                │
│ modes, screen stacks, command palette, themes, workers       │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                        Screen / Widget                       │
│ focus, maximize, selection, scroll, loading, hover, etc.    │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                         DOMNode                              │
│ identifiers, DOM tree, bindings, CSS state, reactives        │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                       MessagePump                            │
│ queue, mount/compose lifecycle, timers, callbacks, idle      │
└──────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
┌──────────────────────────┐   ┌───────────────────────────────┐
│ Reactive / Stylesheet    │   │ Driver / Pilot / WorkerManager│
│ UI invalidation + CSS    │   │ runtime I/O, tests, bg work   │
└──────────────────────────┘   └───────────────────────────────┘
```

`App` inherits `DOMNode`, `Screen` inherits `Widget`, and `Widget` inherits `DOMNode`; `DOMNode` itself inherits `MessagePump`, so the entire visible UI tree sits on top of the same async message-processing substrate.[^3] `DOMNode.__init__` sets up node lists, base CSS styles, inline styles, rendered styles, component-style maps, bindings, and reactive bookkeeping, which is why selectors, style updates, bindings, and state propagation all hang off the same tree object rather than off separate subsystems.[^5] `App.__init__` then layers on feature flags, theme registration, output filters, a Rich console, a `WorkerManager`, screen stacks, and mode tracking, making the app object both the DOM root and the runtime coordinator.[^6]

## Core programming model

### 1. Composition and app structure

The intended authoring model is: subclass `App`, optionally declare `CSS` / `CSS_PATH`, implement `compose()` as a generator of widgets, and then call `run()` / `run_async()`.[^10] The packaged README example embedded in the wheel shows exactly that pattern:

```python
class ClockApp(App):
    CSS = """
    Screen { align: center middle; }
    Digits { width: auto; }
    """

    def compose(self) -> ComposeResult:
        yield Digits("")

    def on_ready(self) -> None:
        self.update_clock()
        self.set_interval(1, self.update_clock)
```

That example is significant because it shows four of Textual's core ideas in one place: declarative CSS, generator-based composition, `query_one()` lookups on the DOM, and timer-driven UI updates via `set_interval()`.[^10][^11]

The standalone `compose()` helper reveals how strict the composition contract is. It iterates the compose generator, requires every yielded object to be a `Widget`, checks that the child has been initialized correctly, and turns bad yields or missing `super().__init__()` calls into `MountError` exceptions with tracebacks pushed back into the originating generator when possible.[^12] In other words, Textual treats the composition phase as a first-class protocol, not as an informal convenience wrapper.[^12]

### 2. DOM, selectors, and styling

`DOMNode` carries the CSS-facing identity of every app/screen/widget via `DEFAULT_CSS`, `DEFAULT_CLASSES`, `COMPONENT_CLASSES`, scoped-CSS behavior, and `_css_type_name` / `_css_type_names` tracking.[^5] During initialization it creates `Styles`, `RenderStyles`, and component-style maps, which is the concrete mechanism behind Textual's selector-driven styling model.[^5]

The stylesheet engine is more than a parser. `Stylesheet` stores source provenance, variables, parsed-rule caches, and style caches; it can read CSS from files or strings, preserve source/tie-break ordering, distinguish widget-default CSS from user CSS, and reparses lazily only when required.[^13] Its error renderer can also show source snippets with filename, line, and column information, which is a strong signal that Textual considers CSS authoring/debugging a first-class developer workflow, not an afterthought.[^13]

There is also a notable scope rule: `App.CSS_PATH` and `Screen.CSS_PATH` both load app-wide stylesheets, and `Screen` explicitly documents that its inline/file CSS applies to the whole app rather than only to the screen object.[^14]

### 3. Reactivity and invalidation

`Reactive` is the state primitive that makes Textual feel "live." Each reactive descriptor can independently control layout invalidation, repaint invalidation, initialization behavior, "always update" semantics, computed/reactive relationships, recomposition, binding refresh, and automatic class toggling.[^15] On write, the descriptor validates via `validate_*` / `_validate_*`, updates truthiness-driven CSS classes, runs watchers, optionally runs computes, refreshes bindings, and finally calls `refresh()` with the right repaint/layout/recompose flags.[^16]

Textual also supports async watchers without forcing app authors to hand-roll event-loop plumbing. If a watch callback returns an awaitable, `invoke_watcher()` schedules it via `call_next()`, and once it completes, Textual posts a callback that reruns reactive computes so derived state stays coherent.[^17] That design makes reactives closer to a structured invalidation system than to plain Python descriptors.[^15][^17]

### 4. Message pump, lifecycle, and scheduling

`MessagePump` is the runtime spine. It owns the message queue, mounted event, timers, disabled-message set, and `message_signal`, plus the temporary message-prevention stack used to suppress cascades during state changes.[^4] Before the main loop starts, `_pre_process()` always dispatches `Compose` and `Mount`, then sets the mounted event so awaited mount operations can continue; after that, `_process_messages_loop()` continually drains the queue, coalesces replaceable messages, dispatches them, publishes signals, injects `Idle` when appropriate, and flushes deferred callbacks.[^18]

The scheduling helpers (`set_timer()`, `set_interval()`, `call_after_refresh()`, `call_later()`, and `call_next()`) all live on `MessagePump`, which means the same timing/callback model is available uniformly on apps, screens, and widgets.[^11][^19] Textual even warns in debug mode when a non-event message handler exceeds the configured slow threshold and suggests using a worker to avoid UI freezes.[^18]

## Major subsystems

### App, screens, and modes

`App` defines `MODES`, `DEFAULT_MODE`, and `SCREENS`, and at runtime stores a dedicated `_screen_stacks` list per mode.[^6] That makes screen navigation more structured than a simple modal stack: a Textual app can model multiple independent navigation stacks, each with its own base screen.[^6]

`Screen` is a `Widget`, but it adds app-wide concerns such as focus ownership, title/subtitle overrides, maximize state, selection state, command providers, and screen-specific breakpoint overrides.[^20] Its default CSS also shows that a screen is conceptually "the terminal surface": vertical layout, `overflow-y: auto`, background handling, inline-mode tweaks, and selection visuals are all defined there rather than in `App`.[^20]

### Widgets and background work

`Widget` layers a large amount of standardized UI state on top of `DOMNode`: focusability, hover/focus pseudo-classes, loading, scrolling, virtual size, link styling, scrollbars, and maximize/selection behavior are all already represented as reactives or class variables on the base widget type.[^21] This is why many Textual widgets feel consistent out of the box: the common interaction/state model is embedded into the base class rather than reinvented per widget.[^21]

Background work is likewise a built-in concern. Each `App` creates a `WorkerManager`, every DOM node exposes it through `.workers`, and `Widget.run_worker()` can create thread or async workers, group them, cancel earlier work in the same group, and safely proxy creation through `call_from_thread()` when invoked off the main thread.[^6][^22] The manager itself supports group/node cancellation and "exclusive" workers that replace older work in the same group, which is useful for live-search, background loading, and debounced refresh patterns.[^22]

### Command palette

The command palette is not just a demo widget; it is built into the app model. `App` enables it by default, reserves `ctrl+p` as the default launch binding, and keeps a set of registered command providers on the app object.[^23] `CommandPalette` is implemented as a `SystemModalScreen` with its own CSS, bindings, input/results composition, and lifecycle hooks.[^24]

The provider model is especially important. When mounted, the command palette records the calling screen, merges app-level providers with screen-level providers, constructs provider instances, and begins gathering commands; when it unmounts, it asynchronously shuts those providers down.[^24] Integration is simple on the consuming side: `App.search_commands()` and `App.search_themes()` just push a `CommandPalette` screen with the relevant providers, which is a nice example of a sophisticated built-in feature still being surfaced through the same screen stack API as user-defined screens.[^25]

## Testing and developer experience

Textual's testing story is unusually strong for a terminal UI framework. `App.run_test()` is an async context manager that defaults to `headless=True`, can pin terminal size, can selectively enable tooltips/notifications, and can install a `message_hook` that observes every message arriving at every message pump in the app.[^26] It starts the app in the background, waits for startup readiness, yields a `Pilot`, then shuts down cleanly and re-raises the app exception if the test caused a panic so the test framework sees the real failure.[^27]

`Pilot` is the programmable driver for those tests. It can press keys, resize the terminal, and synthesize mouse down/up/click operations against either concrete widgets or selectors, waiting for the screen to settle between actions.[^28] This effectively gives Textual a built-in UI automation layer that runs against the same application logic and event loop as production code.[^26][^28]

For day-to-day development, the packaged metadata recommends installing `textual-dev` alongside `textual`, and its embedded README explains that the dev console can connect from another terminal to show system messages, events, logged output, and print output.[^10][^29] The package metadata also explicitly notes that Textual is async internally but does not force users to adopt async everywhere if they do not need it, which is an important part of its ergonomics story.[^10]

## Browser and web story

Textual's own metadata says the framework can run "in the terminal or a web browser" and documents two publishing routes: local sharing with `textual serve "python -m textual"` and broader serving through Textual Web.[^8] The core package includes a `WebDriver` whose module docstring defines a packet protocol, whose `is_web` property returns `True`, and whose `write()` / `write_meta()` methods encode display and metadata packets for a controlling process such as `textual-web` or `textual-serve`.[^9]

The remote/browser path is not a separate UI model; it is the same app model underneath a different driver. `Driver` defines generic capabilities such as `is_web`, `open_url()`, and `deliver_binary()`, while `WebDriver` overrides those capabilities by emitting metadata packets and chunked binary-delivery messages to the controlling process.[^30][^31] `WebDriver.start_application_mode()` also makes the relationship explicit by switching to remote/application mode, sending a magic handshake line, posting initial resize/focus state, and starting a background input thread that reconstructs Textual events from streamed packets.[^9]

The practical takeaway is that Textual's browser strategy is driver-based rather than framework-fork-based: app authors still write `App` / `Screen` / `Widget` code, while the web-specific behavior lives in the transport/driver layer and the serving companion referenced by the docs.[^8][^9][^30]

## Key repositories summary

| Repository | Purpose | Why it matters |
|---|---|---|
| [Textualize/textual](https://github.com/Textualize/textual) | Core framework repo | Defines the runtime architecture, packaging metadata, CSS system, drivers, widgets, testing API, and command palette.[^2][^3][^13] |
| [Textualize/textual-web](https://github.com/Textualize/textual-web) | Companion web-serving project | Referenced by Textual's packaged README as the route for serving apps beyond local `textual serve`.[^8] |

## Confidence Assessment

High confidence: the architectural description in this report is grounded in the installed `textual 8.1.0` source tree and wheel metadata, including exact line-number citations for `App`, `Screen`, `Widget`, `DOMNode`, `MessagePump`, `Reactive`, the stylesheet engine, testing helpers, and the web driver.[^1][^3][^4][^9]

Moderate confidence: the browser/publication section is accurate about the core framework side of the integration, because the package metadata and `WebDriver` make that path explicit, but I did not fully reverse-engineer the separate [Textualize/textual-web](https://github.com/Textualize/textual-web) service internals in this report.[^8][^9]

Moderate confidence on version alignment: the locally installed code I cited is `8.1.0`, while upstream `main` currently advertises `8.1.1`; nothing I found suggests a major architectural shift, but exact implementation details can differ slightly between those two revisions.[^1][^2]

## Footnotes

[^1]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual-8.1.0.dist-info\METADATA:1-25,49-53`.

[^2]: `[Textualize/textual](https://github.com/Textualize/textual)` `pyproject.toml:1-4` (commit `0f0849fd37fbd0d4d6f81889476c22340129df67`).

[^3]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\app.py:296-359`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\dom.py:132-176`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\widget.py:282-308`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\screen.py:145-200`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\message_pump.py:115-158`.

[^4]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\message_pump.py:118-171,198-218,335-354,550-613,634-741`.

[^5]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\dom.py:136-153,186-230`.

[^6]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\app.py:361-399,403-445,573-619,686-699`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\features.py:10-29`.

[^7]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\reactive.py:124-176,316-369,377-435`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\command.py:522-699`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\worker_manager.py:23-119`.

[^8]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual-8.1.0.dist-info\METADATA:240-256`.

[^9]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\drivers\web_driver.py:1-10,41-107,139-182,297-354`.

[^10]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual-8.1.0.dist-info\METADATA:70-73,77-113,183-189,213-233`.

[^11]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\message_pump.py:418-449`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\app.py:2083-2145`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\pilot.py:76-99`.

[^12]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\compose.py:12-99`.

[^13]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\css\stylesheet.py:44-120,141-155,159-239,240-380`.

[^14]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\app.py:409-412`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\screen.py:157-168`.

[^15]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\reactive.py:124-176`.

[^16]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\reactive.py:316-369,437-502`.

[^17]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\reactive.py:82-121,377-435`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\message_pump.py:507-520`.

[^18]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\message_pump.py:528-583,595-613,649-741`.

[^19]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\message_pump.py:378-518`.

[^20]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\screen.py:145-260`.

[^21]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\widget.py:282-420`.

[^22]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\dom.py:475-478`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\widget.py:494-540`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\worker_manager.py:65-180`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\app.py:614-615`.

[^23]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\app.py:427-445`.

[^24]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\command.py:522-699,768-831`.

[^25]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\app.py:1904-1935`.

[^26]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\app.py:2083-2145`.

[^27]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\app.py:2149-2168`.

[^28]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\pilot.py:62-99,100-249`.

[^29]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual-8.1.0.dist-info\METADATA:183-189,213-223`.

[^30]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\driver.py:17-60,195-219`; `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\app.py:616-617`.

[^31]: `C:\Users\thoma\AppData\Roaming\Python\Python313\site-packages\textual\drivers\web_driver.py:260-354`.
