from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path
from typing import cast

from pydantic import ValidationError
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Markdown,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from cwmem.core.models import CreateEdgeInput, CreateEntryInput, TagMutationInput
from cwmem.output.envelope import AppError
from cwmem.ui.actions import add_entry_action, link_resources_action, mutate_tags_action
from cwmem.ui.services import MemoryUIService
from cwmem.ui.view_models import (
    dashboard_markdown,
    edge_row,
    entry_row,
    event_row,
    mutation_markdown,
    pretty_json,
    related_row,
    resource_markdown,
    search_row,
)


class CwmemCommandProvider(Provider):
    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        app = cast(CwmemTuiApp, self.app)
        commands = [
            (
                "open dashboard",
                partial(app.activate_tab, "dashboard-tab"),
                "Show repository status",
            ),
            ("open entries", partial(app.activate_tab, "entries-tab"), "Browse entries"),
            ("open search", partial(app.activate_tab, "search-tab"), "Run hybrid search"),
            ("open graph", partial(app.activate_tab, "graph-tab"), "Inspect related resources"),
            ("open log", partial(app.activate_tab, "log-tab"), "Browse the event log"),
            ("open write", partial(app.activate_tab, "write-tab"), "Create or link memory"),
            ("refresh current", app.action_refresh_current, "Reload the active tab"),
        ]
        for command, action, help_text in commands:
            score = matcher.match(command)
            if score > 0:
                yield Hit(score, matcher.highlight(command), action, help=help_text)


class CwmemTuiApp(App[None]):
    CSS_PATH = "cwmem.tcss"
    COMMANDS = App.COMMANDS | {CwmemCommandProvider}
    BINDINGS = [
        Binding("f1", "show_dashboard", "Dashboard"),
        Binding("f2", "show_entries", "Entries"),
        Binding("f3", "show_search", "Search"),
        Binding("f4", "show_graph", "Graph"),
        Binding("f5", "show_log", "Log"),
        Binding("f6", "show_write", "Write"),
        Binding("ctrl+r", "refresh_current", "Refresh"),
        Binding("escape", "focus_table", "Focus table", show=False),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, *, root: Path) -> None:
        super().__init__()
        self.root = root
        self.service = MemoryUIService(root)
        self._entry_row_ids: list[str] = []
        self._search_row_ids: list[str] = []
        self._event_row_ids: list[str] = []
        self._related_row_ids: list[str] = []
        self._selected_resource_id = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="main-tabs", initial="dashboard-tab"):
            with TabPane("Dashboard", id="dashboard-tab"):
                yield Markdown(
                    self._placeholder("Dashboard", "Loading repository status..."),
                    id="dashboard-markdown",
                )
            with TabPane("Entries", id="entries-tab"):
                with Vertical(classes="tab-shell"):
                    with Horizontal(classes="toolbar"):
                        yield Input(placeholder="tag1,tag2", id="entries-tags")
                        yield Input(placeholder="type", id="entries-type")
                        yield Input(placeholder="status", id="entries-status")
                        yield Input(placeholder="author", id="entries-author")
                        yield Input(value="50", id="entries-limit")
                        yield Button("Refresh", id="entries-refresh", variant="primary")
                    with Horizontal(classes="two-pane"):
                        yield DataTable(id="entries-table", classes="results-table")
                        yield Markdown(
                            self._placeholder("Entries", "Select an entry to inspect it."),
                            id="entries-preview",
                            classes="preview",
                        )
            with TabPane("Search", id="search-tab"):
                with Vertical(classes="tab-shell"):
                    with Horizontal(classes="toolbar"):
                        yield Input(placeholder="search query", id="search-q")
                        yield Select(
                            [
                                ("Hybrid", "hybrid"),
                                ("Lexical only", "lexical"),
                                ("Semantic only", "semantic"),
                            ],
                            allow_blank=False,
                            value="hybrid",
                            id="search-mode",
                        )
                        yield Checkbox("Expand graph", id="search-expand")
                        yield Input(placeholder="tag", id="search-tag")
                        yield Input(placeholder="type", id="search-type")
                        yield Input(placeholder="author", id="search-author")
                    with Horizontal(classes="toolbar"):
                        yield Input(placeholder="from (ISO date)", id="search-from")
                        yield Input(placeholder="to (ISO date)", id="search-to")
                        yield Input(value="20", id="search-limit")
                        yield Button("Search", id="search-run", variant="primary")
                    with Horizontal(classes="two-pane"):
                        yield DataTable(id="search-table", classes="results-table")
                        yield Markdown(
                            self._placeholder("Search", "Run a query to inspect hits."),
                            id="search-preview",
                            classes="preview",
                        )
            with TabPane("Graph", id="graph-tab"):
                with Vertical(classes="tab-shell"):
                    with Horizontal(classes="toolbar"):
                        yield Input(placeholder="resource id", id="graph-resource")
                        yield Input(placeholder="relation filter", id="graph-relation")
                        yield Input(value="1", id="graph-depth")
                        yield Input(value="50", id="graph-limit")
                        yield Button("Load graph", id="graph-run", variant="primary")
                    with Horizontal(classes="graph-pane"):
                        yield DataTable(id="related-table", classes="results-table")
                        with Vertical(classes="graph-right"):
                            yield DataTable(id="edge-table", classes="results-table graph-edges")
                            yield Markdown(
                                self._placeholder(
                                    "Graph",
                                    "Load a resource neighborhood to inspect related items.",
                                ),
                                id="graph-preview",
                                classes="preview",
                            )
            with TabPane("Log", id="log-tab"):
                with Vertical(classes="tab-shell"):
                    with Horizontal(classes="toolbar"):
                        yield Input(placeholder="resource id", id="log-resource")
                        yield Input(placeholder="event type", id="log-event-type")
                        yield Input(placeholder="tag1,tag2", id="log-tags")
                        yield Input(value="50", id="log-limit")
                        yield Button("Refresh log", id="log-refresh", variant="primary")
                    with Horizontal(classes="two-pane"):
                        yield DataTable(id="log-table", classes="results-table")
                        yield Markdown(
                            self._placeholder("Log", "Select an event to inspect it."),
                            id="log-preview",
                            classes="preview",
                        )
            with TabPane("Write", id="write-tab"):
                with Horizontal(classes="two-pane"):
                    with VerticalScroll(id="write-scroll"):
                        yield Static("Selected resource: none", id="write-selected-resource")
                        yield Static("Add entry", classes="section-title")
                        with Horizontal(classes="toolbar"):
                            yield Input(placeholder="title", id="add-title")
                            yield Select(
                                [
                                    ("note", "note"),
                                    ("decision", "decision"),
                                    ("finding", "finding"),
                                    ("standard", "standard"),
                                ],
                                allow_blank=False,
                                value="note",
                                id="add-type",
                            )
                            yield Input(placeholder="author", id="add-author")
                            yield Input(placeholder="tag1,tag2", id="add-tags")
                        yield TextArea(
                            id="add-body",
                            placeholder="Body text for the new memory entry",
                        )
                        with Horizontal(classes="toolbar"):
                            yield Button("Preview add", id="add-preview")
                            yield Button("Apply add", id="add-apply", variant="success")

                        yield Static("Tag resource", classes="section-title")
                        with Horizontal(classes="toolbar"):
                            yield Input(placeholder="resource id", id="tag-resource")
                            yield Input(placeholder="tag1,tag2", id="tag-tags")
                            yield Select(
                                [("Add tags", "add"), ("Remove tags", "remove")],
                                allow_blank=False,
                                value="add",
                                id="tag-mode",
                            )
                        with Horizontal(classes="toolbar"):
                            yield Button("Preview tags", id="tag-preview")
                            yield Button("Apply tags", id="tag-apply", variant="success")

                        yield Static("Link resources", classes="section-title")
                        with Horizontal(classes="toolbar"):
                            yield Input(placeholder="source id", id="link-source")
                            yield Input(placeholder="target id", id="link-target")
                        with Horizontal(classes="toolbar"):
                            yield Input(
                                placeholder="relation",
                                id="link-relation",
                                value="related_to",
                            )
                            yield Input(
                                placeholder="confidence 0-1",
                                id="link-confidence",
                                value="1.0",
                            )
                        with Horizontal(classes="toolbar"):
                            yield Button("Preview link", id="link-preview")
                            yield Button("Apply link", id="link-apply", variant="success")
                    yield Markdown(
                        self._placeholder(
                            "Write preview",
                            "Preview or apply add / tag / link workflows here.",
                        ),
                        id="write-preview",
                        classes="preview",
                    )
        yield Footer()

    def on_mount(self) -> None:
        self.title = "cwmem tui"
        self.sub_title = str(self.root)
        self._configure_table(
            "#entries-table",
            "ID",
            "Type",
            "Status",
            "Title",
            "Author",
            "Updated",
        )
        self._configure_table(
            "#search-table",
            "ID",
            "Kind",
            "Modes",
            "Score",
            "Label",
            "Summary",
        )
        self._configure_table("#log-table", "ID", "Event type", "Occurred", "Summary", "Refs")
        self._configure_table("#related-table", "ID", "Kind", "Depth", "Label", "Path")
        self._configure_table(
            "#edge-table",
            "Edge",
            "Relation",
            "Source",
            "Target",
            "Conf",
            "Provenance",
        )
        self.load_dashboard()
        self.load_entries()
        self.load_log()

    def activate_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = tab_id

    def action_show_dashboard(self) -> None:
        self.activate_tab("dashboard-tab")

    def action_show_entries(self) -> None:
        self.activate_tab("entries-tab")

    def action_show_search(self) -> None:
        self.activate_tab("search-tab")

    def action_show_graph(self) -> None:
        graph_resource = self.query_one("#graph-resource", Input)
        if not graph_resource.value.strip() and self._selected_resource_id:
            graph_resource.value = self._selected_resource_id
        self.activate_tab("graph-tab")

    def action_show_log(self) -> None:
        self.activate_tab("log-tab")

    def action_show_write(self) -> None:
        self.activate_tab("write-tab")

    _TAB_TABLES: dict[str, str] = {
        "entries-tab": "#entries-table",
        "search-tab": "#search-table",
        "graph-tab": "#related-table",
        "log-tab": "#log-table",
    }

    def action_focus_table(self) -> None:
        """Move focus to the primary data table in the active tab."""
        active = self.query_one("#main-tabs", TabbedContent).active
        selector = self._TAB_TABLES.get(active)
        if selector:
            self.query_one(selector, DataTable).focus()

    def _drill_to_graph(self, table_id: str, resource_ids: list[str]) -> None:
        """Navigate the selected table row into the Graph tab."""
        table = self.query_one(table_id, DataTable)
        index = table.cursor_row
        if index < 0 or index >= len(resource_ids):
            return
        resource_id = resource_ids[index]
        self._remember_selected_resource(resource_id)
        self.query_one("#graph-resource", Input).value = resource_id
        self.activate_tab("graph-tab")

    @on(DataTable.RowSelected, "#entries-table")
    def _entries_row_selected(self) -> None:
        self._drill_to_graph("#entries-table", self._entry_row_ids)

    @on(DataTable.RowSelected, "#search-table")
    def _search_row_selected(self) -> None:
        self._drill_to_graph("#search-table", self._search_row_ids)

    @on(DataTable.RowSelected, "#related-table")
    def _related_row_selected(self) -> None:
        self._drill_to_graph("#related-table", self._related_row_ids)

    @on(DataTable.RowSelected, "#log-table")
    def _log_row_selected(self) -> None:
        self._drill_to_graph("#log-table", self._event_row_ids)

    def action_refresh_current(self) -> None:
        active = self.query_one("#main-tabs", TabbedContent).active
        if active == "dashboard-tab":
            self.load_dashboard()
        elif active == "entries-tab":
            self.load_entries()
        elif active == "search-tab":
            if self.query_one("#search-q", Input).value.strip():
                self.run_search()
        elif active == "graph-tab":
            if self.query_one("#graph-resource", Input).value.strip() or self._selected_resource_id:
                self.load_graph()
        elif active == "log-tab":
            self.load_log()

    @on(TabbedContent.TabActivated, "#main-tabs")
    def _tab_activated(self) -> None:
        self.action_refresh_current()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "entries-refresh":
                self.load_entries()
            case "search-run":
                self.run_search()
            case "graph-run":
                self.load_graph()
            case "log-refresh":
                self.load_log()
            case "add-preview":
                self.preview_add_entry()
            case "add-apply":
                self.apply_add_entry()
            case "tag-preview":
                self.preview_tag_change()
            case "tag-apply":
                self.apply_tag_change()
            case "link-preview":
                self.preview_link()
            case "link-apply":
                self.apply_link()

    @on(DataTable.RowHighlighted, "#entries-table")
    @on(DataTable.RowSelected, "#entries-table")
    def _entries_selection_changed(self) -> None:
        if not self.query_one("#entries-table", DataTable).has_focus:
            return
        self._preview_from_mapping("#entries-table", self._entry_row_ids, "#entries-preview")

    @on(DataTable.RowHighlighted, "#search-table")
    @on(DataTable.RowSelected, "#search-table")
    def _search_selection_changed(self) -> None:
        if not self.query_one("#search-table", DataTable).has_focus:
            return
        self._preview_from_mapping("#search-table", self._search_row_ids, "#search-preview")

    @on(DataTable.RowHighlighted, "#log-table")
    @on(DataTable.RowSelected, "#log-table")
    def _log_selection_changed(self) -> None:
        if not self.query_one("#log-table", DataTable).has_focus:
            return
        self._preview_from_mapping("#log-table", self._event_row_ids, "#log-preview")

    @on(DataTable.RowHighlighted, "#related-table")
    @on(DataTable.RowSelected, "#related-table")
    def _related_selection_changed(self) -> None:
        if not self.query_one("#related-table", DataTable).has_focus:
            return
        self._preview_from_mapping("#related-table", self._related_row_ids, "#graph-preview")

    @work(exclusive=True, group="dashboard")
    async def load_dashboard(self) -> None:
        preview = self.query_one("#dashboard-markdown", Markdown)
        preview.update(self._placeholder("Dashboard", "Loading repository status..."))
        try:
            snapshot = await asyncio.to_thread(self.service.dashboard)
        except (AppError, OSError) as exc:
            preview.update(self._error_markdown(exc))
            return
        preview.update(dashboard_markdown(snapshot))

    @work(exclusive=True, group="entries")
    async def load_entries(self) -> None:
        table = self.query_one("#entries-table", DataTable)
        table.loading = True
        try:
            entries = await asyncio.to_thread(
                self.service.list_entries,
                tags=self._split_csv(self.query_one("#entries-tags", Input).value),
                entry_type=self._blank_none(self.query_one("#entries-type", Input).value),
                status=self._blank_none(self.query_one("#entries-status", Input).value),
                author=self._blank_none(self.query_one("#entries-author", Input).value),
                limit=self._int_from_input("#entries-limit", default=50),
            )
        except (AppError, ValidationError, ValueError, OSError) as exc:
            self.query_one("#entries-preview", Markdown).update(self._error_markdown(exc))
            table.loading = False
            return

        table.clear(columns=False)
        self._entry_row_ids = []
        for entry in entries:
            table.add_row(*entry_row(entry), key=entry.public_id)
            self._entry_row_ids.append(entry.public_id)
        table.loading = False
        if self._entry_row_ids:
            self._show_resource_preview(
                self._entry_row_ids[0],
                "#entries-preview",
                remember=not bool(self._selected_resource_id),
            )
            self._focus_table_if_active("#entries-table", "entries-tab")
        else:
            self.query_one("#entries-preview", Markdown).update(
                self._placeholder("Entries", "No entries matched the current filters.")
            )

    @work(exclusive=True, group="search")
    async def run_search(self) -> None:
        query = self.query_one("#search-q", Input).value.strip()
        if not query:
            self.query_one("#search-preview", Markdown).update(
                self._placeholder("Search", "Enter a query before running search.")
            )
            self.query_one("#search-table", DataTable).clear(columns=False)
            self._search_row_ids = []
            return

        table = self.query_one("#search-table", DataTable)
        table.loading = True
        try:
            mode = str(self.query_one("#search-mode", Select).value)
            results = await asyncio.to_thread(
                self.service.search,
                q=query,
                tag=self._blank_none(self.query_one("#search-tag", Input).value),
                search_type=self._blank_none(self.query_one("#search-type", Input).value),
                author=self._blank_none(self.query_one("#search-author", Input).value),
                date_from=self._blank_none(self.query_one("#search-from", Input).value),
                date_to=self._blank_none(self.query_one("#search-to", Input).value),
                lexical_only=mode == "lexical",
                semantic_only=mode == "semantic",
                expand_graph=self.query_one("#search-expand", Checkbox).value,
                limit=self._int_from_input("#search-limit", default=20),
            )
        except (AppError, ValidationError, RuntimeError, ValueError, OSError) as exc:
            self.query_one("#search-preview", Markdown).update(self._error_markdown(exc))
            table.loading = False
            return

        table.clear(columns=False)
        self._search_row_ids = []
        for hit, resource in results:
            table.add_row(*search_row(hit, resource), key=hit.resource_id)
            self._search_row_ids.append(hit.resource_id)
        table.loading = False
        if self._search_row_ids:
            self._show_resource_preview(
                self._search_row_ids[0],
                "#search-preview",
                remember=False,
            )
            self._focus_table_if_active("#search-table", "search-tab")
        else:
            self.query_one("#search-preview", Markdown).update(
                self._placeholder("Search", "No search hits matched the current query.")
            )

    @work(exclusive=True, group="graph")
    async def load_graph(self) -> None:
        resource_input = self.query_one("#graph-resource", Input)
        resource_id = resource_input.value.strip() or self._selected_resource_id
        if resource_id and not resource_input.value.strip():
            resource_input.value = resource_id
        if not resource_id:
            self.query_one("#graph-preview", Markdown).update(
                self._placeholder("Graph", "Enter a resource ID before loading the graph.")
            )
            return

        related_table = self.query_one("#related-table", DataTable)
        edge_table = self.query_one("#edge-table", DataTable)
        related_table.loading = True
        edge_table.loading = True
        try:
            related_hits, neighborhood = await asyncio.gather(
                asyncio.to_thread(
                    self.service.related,
                    resource_id=resource_id,
                    relation_type=self._blank_none(self.query_one("#graph-relation", Input).value),
                    depth=self._int_from_input("#graph-depth", default=1),
                    limit=self._int_from_input("#graph-limit", default=50),
                ),
                asyncio.to_thread(
                    self.service.graph,
                    resource_id=resource_id,
                    relation_type=self._blank_none(self.query_one("#graph-relation", Input).value),
                    depth=self._int_from_input("#graph-depth", default=1),
                    limit=self._int_from_input("#graph-limit", default=50),
                ),
            )
        except (AppError, ValidationError, ValueError, OSError) as exc:
            self.query_one("#graph-preview", Markdown).update(self._error_markdown(exc))
            related_table.loading = False
            edge_table.loading = False
            return

        related_table.clear(columns=False)
        self._related_row_ids = []
        for hit in related_hits:
            related_table.add_row(*related_row(hit), key=hit.resource_id)
            self._related_row_ids.append(hit.resource_id)

        edge_table.clear(columns=False)
        for edge in neighborhood.edges:
            edge_table.add_row(*edge_row(edge), key=edge.public_id)

        related_table.loading = False
        edge_table.loading = False
        if self._related_row_ids or neighborhood.edges:
            self._show_resource_preview(resource_id, "#graph-preview")
            self._focus_table_if_active("#related-table", "graph-tab")
        else:
            self.query_one("#graph-preview", Markdown).update(
                self._placeholder(
                    "Graph",
                    f"No graph neighbors were found for `{resource_id}`. "
                    "Select another resource from Entries, Search, or Log, "
                    "or create a link from the Write tab.",
                )
            )
            self._remember_selected_resource(resource_id)

    @work(exclusive=True, group="log")
    async def load_log(self) -> None:
        table = self.query_one("#log-table", DataTable)
        table.loading = True
        try:
            events = await asyncio.to_thread(
                self.service.log,
                resource=self._blank_none(self.query_one("#log-resource", Input).value),
                event_type=self._blank_none(self.query_one("#log-event-type", Input).value),
                tags=self._split_csv(self.query_one("#log-tags", Input).value),
                limit=self._int_from_input("#log-limit", default=50),
            )
        except (AppError, ValidationError, ValueError, OSError) as exc:
            self.query_one("#log-preview", Markdown).update(self._error_markdown(exc))
            table.loading = False
            return

        table.clear(columns=False)
        self._event_row_ids = []
        for event in events:
            table.add_row(*event_row(event), key=event.public_id)
            self._event_row_ids.append(event.public_id)
        table.loading = False
        if self._event_row_ids:
            self._show_resource_preview(
                self._event_row_ids[0],
                "#log-preview",
                remember=False,
            )
            self._focus_table_if_active("#log-table", "log-tab")
        else:
            self.query_one("#log-preview", Markdown).update(
                self._placeholder("Log", "No events matched the current filters.")
            )

    @work(exclusive=True, group="mutations")
    async def preview_add_entry(self) -> None:
        await self._run_add_entry(dry_run=True)

    @work(exclusive=True, group="mutations")
    async def apply_add_entry(self) -> None:
        await self._run_add_entry(dry_run=False)

    @work(exclusive=True, group="mutations")
    async def preview_tag_change(self) -> None:
        await self._run_tag_change(dry_run=True)

    @work(exclusive=True, group="mutations")
    async def apply_tag_change(self) -> None:
        await self._run_tag_change(dry_run=False)

    @work(exclusive=True, group="mutations")
    async def preview_link(self) -> None:
        await self._run_link(dry_run=True)

    @work(exclusive=True, group="mutations")
    async def apply_link(self) -> None:
        await self._run_link(dry_run=False)

    async def _run_add_entry(self, *, dry_run: bool) -> None:
        preview = self.query_one("#write-preview", Markdown)
        preview.update(self._placeholder("Write preview", "Preparing entry mutation preview..."))
        try:
            payload = CreateEntryInput.model_validate(
                {
                    "title": self.query_one("#add-title", Input).value,
                    "body": self.query_one("#add-body", TextArea).text,
                    "type": str(self.query_one("#add-type", Select).value),
                    "author": self._blank_none(self.query_one("#add-author", Input).value),
                    "tags": self._split_csv(self.query_one("#add-tags", Input).value),
                }
            )
            result = await asyncio.to_thread(
                add_entry_action,
                self.root,
                payload,
                dry_run=dry_run,
            )
        except (AppError, ValidationError, ValueError, OSError) as exc:
            preview.update(self._error_markdown(exc))
            return

        preview.update(mutation_markdown(result))
        if not dry_run:
            entry = result.get("entry")
            if isinstance(entry, dict):
                self._remember_selected_resource(str(entry.get("public_id", "")))
            self.notify("Entry created.", severity="information")
            self.load_dashboard()
            self.load_entries()

    async def _run_tag_change(self, *, dry_run: bool) -> None:
        preview = self.query_one("#write-preview", Markdown)
        preview.update(self._placeholder("Write preview", "Preparing tag mutation preview..."))
        try:
            payload = TagMutationInput.model_validate(
                {
                    "resource_id": self.query_one("#tag-resource", Input).value,
                    "tags": self._split_csv(self.query_one("#tag-tags", Input).value),
                }
            )
            add_mode = str(self.query_one("#tag-mode", Select).value) == "add"
            result = await asyncio.to_thread(
                mutate_tags_action,
                self.root,
                payload,
                add=add_mode,
                dry_run=dry_run,
            )
        except (AppError, ValidationError, ValueError, OSError) as exc:
            preview.update(self._error_markdown(exc))
            return

        preview.update(mutation_markdown(result))
        if not dry_run:
            entry = result.get("entry")
            if isinstance(entry, dict):
                self._remember_selected_resource(str(entry.get("public_id", "")))
            self.notify("Tag mutation finished.", severity="information")
            self.load_entries()
            self.load_dashboard()

    async def _run_link(self, *, dry_run: bool) -> None:
        preview = self.query_one("#write-preview", Markdown)
        preview.update(self._placeholder("Write preview", "Preparing link mutation preview..."))
        try:
            payload = CreateEdgeInput.model_validate(
                {
                    "source_id": self.query_one("#link-source", Input).value,
                    "target_id": self.query_one("#link-target", Input).value,
                    "relation_type": self.query_one("#link-relation", Input).value,
                    "provenance": "explicit_user",
                    "confidence": self._float_from_input("#link-confidence", default=1.0),
                }
            )
            result = await asyncio.to_thread(
                link_resources_action,
                self.root,
                payload,
                dry_run=dry_run,
            )
        except (AppError, ValidationError, ValueError, OSError) as exc:
            preview.update(self._error_markdown(exc))
            return

        preview.update(mutation_markdown(result))
        if not dry_run:
            self.notify("Link created.", severity="information")
            self.load_graph()
            self.load_dashboard()

    def _preview_from_mapping(
        self,
        table_id: str,
        resource_ids: list[str],
        preview_id: str,
    ) -> None:
        table = self.query_one(table_id, DataTable)
        index = table.cursor_row
        if index < 0 or index >= len(resource_ids):
            return
        self._show_resource_preview(resource_ids[index], preview_id)

    def _show_resource_preview(
        self,
        resource_id: str,
        preview_id: str,
        *,
        remember: bool = True,
    ) -> None:
        if not resource_id:
            return
        preview = self.query_one(preview_id, Markdown)
        try:
            resource = self.service.preview_resource(resource_id)
        except (AppError, OSError) as exc:
            preview.update(self._error_markdown(exc))
            return
        preview.update(resource_markdown(resource))
        if remember:
            self._remember_selected_resource(resource_id)

    def _remember_selected_resource(self, resource_id: str) -> None:
        if not resource_id:
            return
        self._selected_resource_id = resource_id
        self.query_one("#write-selected-resource", Static).update(
            f"Selected resource: {resource_id}"
        )
        tag_input = self.query_one("#tag-resource", Input)
        if not tag_input.value.strip():
            tag_input.value = resource_id
        link_source = self.query_one("#link-source", Input)
        if not link_source.value.strip():
            link_source.value = resource_id
        graph_resource = self.query_one("#graph-resource", Input)
        if not graph_resource.value.strip():
            graph_resource.value = resource_id
            if self.query_one("#main-tabs", TabbedContent).active == "graph-tab":
                self.load_graph()

    def _focus_table_if_active(self, table_selector: str, tab_id: str) -> None:
        """Focus the table only when its tab is currently visible."""
        if self.query_one("#main-tabs", TabbedContent).active == tab_id:
            self.query_one(table_selector, DataTable).focus()

    def _configure_table(self, selector: str, *columns: str) -> None:
        table = self.query_one(selector, DataTable)
        table.cursor_type = "row"
        table.add_columns(*columns)

    def _int_from_input(self, selector: str, *, default: int) -> int:
        raw = self.query_one(selector, Input).value.strip()
        if not raw:
            return default
        return int(raw)

    def _float_from_input(self, selector: str, *, default: float) -> float:
        raw = self.query_one(selector, Input).value.strip()
        if not raw:
            return default
        return float(raw)

    def _split_csv(self, raw: str) -> list[str]:
        return [part.strip() for part in raw.split(",") if part.strip()]

    def _blank_none(self, raw: str) -> str | None:
        value = raw.strip()
        return value or None

    def _placeholder(self, title: str, body: str) -> str:
        return f"# {title}\n\n{body}"

    def _error_markdown(
        self,
        exc: AppError | ValidationError | RuntimeError | ValueError | OSError,
    ) -> str:
        if isinstance(exc, AppError):
            lines = [
                "# Error",
                "",
                exc.error.message,
                "",
                f"- Suggested action: {exc.error.suggested_action}",
            ]
            if exc.error.details:
                lines.extend(["", "```json", pretty_json(exc.error.details), "```"])
            return "\n".join(lines)
        if isinstance(exc, ValidationError):
            return "\n".join(
                [
                    "# Validation error",
                    "",
                    "```json",
                    pretty_json(exc.errors(include_url=False, include_context=False)),
                    "```",
                ]
            )
        return f"# Error\n\n{exc}"
