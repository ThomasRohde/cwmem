from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import DataTable, Input, Select, TabbedContent, TextArea

from cwmem.tui import CwmemTuiApp
from tests.phase2_helpers import extract_entry, init_repo, run_ok
from tests.phase3_helpers import select_count


def _related_resource_ids(payload: dict[str, object]) -> set[str]:
    result = payload["result"]
    assert isinstance(result, dict), result
    hits = result["hits"]
    assert isinstance(hits, list), hits
    return {
        str(hit["resource_id"])
        for hit in hits
        if isinstance(hit, dict) and isinstance(hit.get("resource_id"), str)
    }


def test_tui_app_supports_exploration_and_safe_write_flows(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)
    anchor = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "TUI anchor entry",
            "--type",
            "decision",
            "Anchor content for the Textual app test.",
        )
    )

    created_entry_id = ""

    async def scenario() -> None:
        nonlocal created_entry_id

        app = CwmemTuiApp(root=tmp_path)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            assert app.query_one("#entries-table", DataTable).row_count == 1

            app.action_show_search()
            await pilot.pause()
            app.query_one("#search-q", Input).value = "anchor content"
            app.query_one("#search-mode", Select).value = "lexical"
            app.run_search()
            await pilot.pause()
            assert anchor["public_id"] in app._search_row_ids

            app.action_show_write()
            await pilot.pause()
            app.query_one("#add-title", Input).value = "Created in the TUI"
            app.query_one("#add-tags", Input).value = "interactive"
            app.query_one("#add-body", TextArea).load_text("This entry was created from the TUI.")

            await app._run_add_entry(dry_run=True)
            assert select_count(tmp_path, "entries") == 1

            await app._run_add_entry(dry_run=False)
            await pilot.pause()
            assert select_count(tmp_path, "entries") == 2
            created_entry_id = app.service.list_entries(limit=10)[-1].public_id
            assert created_entry_id.startswith("mem-")

            app.query_one("#tag-resource", Input).value = anchor["public_id"]
            app.query_one("#tag-tags", Input).value = "interactive"
            app.query_one("#tag-mode", Select).value = "add"
            await app._run_tag_change(dry_run=False)
            await pilot.pause()

            app.query_one("#link-source", Input).value = anchor["public_id"]
            app.query_one("#link-target", Input).value = created_entry_id
            app.query_one("#link-relation", Input).value = "related_to"
            await app._run_link(dry_run=False)
            await pilot.pause()

    asyncio.run(scenario())

    anchor_after = extract_entry(run_ok(run_cli, tmp_path, "get", anchor["public_id"]))
    assert "interactive" in anchor_after["tags"]

    related_payload = run_ok(run_cli, tmp_path, "related", anchor["public_id"], "--depth", "1")
    assert created_entry_id in _related_resource_ids(related_payload)


def test_tui_function_keys_switch_tabs_and_load_selected_graph(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)
    anchor = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Graph anchor",
            "--type",
            "decision",
            "Anchor content for graph loading.",
        )
    )
    neighbor = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Graph neighbor",
            "--type",
            "note",
            "Neighbor content for graph loading.",
        )
    )
    run_ok(
        run_cli,
        tmp_path,
        "link",
        anchor["public_id"],
        neighbor["public_id"],
        "--relation",
        "references",
        "--provenance",
        "explicit_user",
    )

    async def scenario() -> None:
        app = CwmemTuiApp(root=tmp_path)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            app.query_one("#graph-resource", Input).value = ""

            await pilot.press("f4")
            await pilot.pause()

            assert app.query_one("#main-tabs", TabbedContent).active == "graph-tab"
            assert app.query_one("#graph-resource", Input).value == anchor["public_id"]
            assert app.query_one("#related-table", DataTable).row_count == 1

    asyncio.run(scenario())


def test_tui_graph_layout_keeps_widgets_within_graph_tab(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)
    anchor = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Graph layout anchor",
            "--type",
            "decision",
            "Anchor content for graph layout testing.",
        )
    )
    neighbor = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Graph layout neighbor",
            "--type",
            "note",
            "Neighbor content for graph layout testing.",
        )
    )
    run_ok(
        run_cli,
        tmp_path,
        "link",
        anchor["public_id"],
        neighbor["public_id"],
        "--relation",
        "references",
        "--provenance",
        "explicit_user",
    )

    async def scenario() -> None:
        app = CwmemTuiApp(root=tmp_path)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            await pilot.press("f4")
            await pilot.pause()

            graph_tab = app.query_one("#graph-tab")
            related = app.query_one("#related-table", DataTable)
            edge = app.query_one("#edge-table", DataTable)
            preview = app.query_one("#graph-preview")

            graph_right_edge = graph_tab.region.x + graph_tab.size.width
            assert related.region.x + related.size.width <= graph_right_edge
            assert edge.region.x + edge.size.width <= graph_right_edge
            assert preview.region.x + preview.size.width <= graph_right_edge

    asyncio.run(scenario())


def test_tui_graph_loads_when_tabbed_content_active_changes(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)
    anchor = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Tabbed graph anchor",
            "--type",
            "decision",
            "Anchor content for tab activation testing.",
        )
    )
    neighbor = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Tabbed graph neighbor",
            "--type",
            "note",
            "Neighbor content for tab activation testing.",
        )
    )
    run_ok(
        run_cli,
        tmp_path,
        "link",
        anchor["public_id"],
        neighbor["public_id"],
        "--relation",
        "references",
        "--provenance",
        "explicit_user",
    )

    async def scenario() -> None:
        app = CwmemTuiApp(root=tmp_path)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.query_one("#main-tabs", TabbedContent).active = "graph-tab"
            await pilot.pause()
            await pilot.pause()

            assert app.query_one("#graph-resource", Input).value == anchor["public_id"]
            assert app.query_one("#related-table", DataTable).row_count == 1

    asyncio.run(scenario())
