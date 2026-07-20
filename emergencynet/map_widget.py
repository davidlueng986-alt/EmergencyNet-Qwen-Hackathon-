"""Live map widget for the base dashboard.

Renders an HTML map with three marker types:
  - 🔵 Field-team radios (Heltec V4 nodes) — from ``MeshPositionTracker``
  - 🟠 Civilian distress reports — from ``CivilianIntake``
  - 🔴/🟡/🟢 Incident patient zones — from the patient list (optional)

Uses Folium to generate self-contained HTML that drops into a
``gradio.HTML`` component or any other HTML host. No live JS; the
dashboard re-renders the HTML on each refresh tick.

Folium is a minor dep (`pip install folium`); if missing, this module
falls back to a simple textual rendering so the dashboard still works.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# Default centre — Hong Kong island (used if no GPS data yet)
DEFAULT_CENTRE = (22.3193, 114.1694)
DEFAULT_ZOOM = 11


def render_map_html(
    field_nodes: Optional[List[Dict[str, Any]]] = None,
    civilian_reports: Optional[List[Dict[str, Any]]] = None,
    patient_zones: Optional[List[Dict[str, Any]]] = None,
    centre: Optional[Tuple[float, float]] = None,
    zoom: int = DEFAULT_ZOOM,
) -> str:
    """Build a self-contained HTML map.

    Args:
        field_nodes:      list from ``MeshPositionTracker.snapshot()``
        civilian_reports: list from ``CivilianIntake.snapshot()``
        patient_zones:    optional list of {lat, lon, tag, patient_id}
        centre:           (lat, lon) — defaults to centroid of all
                          markers, or Hong Kong if no markers
        zoom:             initial zoom (folium default 11 is good for HK)
    """
    field_nodes = field_nodes or []
    civilian_reports = civilian_reports or []
    patient_zones = patient_zones or []

    try:
        import folium
    except ImportError:
        return _fallback_text(field_nodes, civilian_reports, patient_zones)

    # Compute centre if not provided
    if centre is None:
        centre = _centre_of_markers(field_nodes, civilian_reports, patient_zones)

    fmap = folium.Map(
        location=list(centre),
        zoom_start=zoom,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    # ---------- Field-team radios (blue) ----------
    for n in field_nodes:
        popup_html = (
            f"<b>{n.get('name', n['node_id'])}</b><br>"
            f"<small>{n.get('short_name', '')}</small><br>"
            f"RSSI: {n.get('rssi', '?')}<br>"
            f"SNR: {n.get('snr', '?')}<br>"
            f"Last seen: {n.get('age_s', '?')}s ago"
        )
        folium.CircleMarker(
            location=[n["lat"], n["lon"]],
            radius=8,
            color="#1f6feb",
            fill=True,
            fill_color="#1f6feb",
            fill_opacity=0.8,
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"📻 {n.get('short_name') or n['node_id']}",
        ).add_to(fmap)

    # ---------- Civilian distress reports (orange/red by severity) ----------
    for r in civilian_reports:
        if r.get("acknowledged"):
            continue
        popup_html = (
            f"<b>Civilian distress</b><br>"
            f"Severity: {r.get('severity_hint', '?')}<br>"
            f"Lang: {r.get('language', '?')}<br>"
            f"Summary: {r.get('summary_en', '')[:200]}<br>"
            f"<small>{r.get('age_s', '?')}s ago</small>"
        )
        folium.Marker(
            location=[r["lat"], r["lon"]],
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"🆘 {r.get('severity_hint','?').upper()}",
            icon=folium.Icon(
                color=_folium_color_from_severity(r.get("severity_hint", "moderate")),
                icon="exclamation-sign",
            ),
        ).add_to(fmap)

    # ---------- Patient zones (RED/YELLOW/GREEN/BLACK triage tags) ----------
    for p in patient_zones:
        tag = p.get("tag", "UNKNOWN")
        col = _triage_tag_color(tag)
        popup_html = (
            f"<b>Patient {p.get('patient_id', '?')}</b><br>"
            f"Tag: {tag}<br>"
            f"Score: {p.get('priority_score', '?')}<br>"
            f"Zone: {p.get('zone', '?')}"
        )
        folium.CircleMarker(
            location=[p["lat"], p["lon"]],
            radius=6,
            color=col,
            fill=True,
            fill_color=col,
            fill_opacity=0.9,
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"🏥 {tag}",
        ).add_to(fmap)

    # Legend
    legend_html = """
    <div style="
        position: absolute; bottom: 20px; left: 20px; z-index: 9999;
        background: white; padding: 10px 12px; border-radius: 6px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.2); font: 12px sans-serif;">
      <b>Legend</b><br>
      <span style="color:#1f6feb;">●</span> Field radio<br>
      <span style="color:#d9000a;">▲</span> Civilian critical<br>
      <span style="color:#ff6b00;">▲</span> Civilian high<br>
      <span style="color:#dc2626;">●</span> RED tag patient<br>
      <span style="color:#eab308;">●</span> YELLOW tag patient<br>
      <span style="color:#16a34a;">●</span> GREEN tag patient<br>
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(legend_html))

    import html as html_mod
    raw = fmap.get_root().render()
    return (
        '<div style="width:100%;height:600px;">'
        f'<iframe srcdoc="{html_mod.escape(raw)}" '
        'style="width:100%;height:100%;border:none;" '
        'sandbox="allow-scripts allow-same-origin">'
        '</iframe></div>'
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _centre_of_markers(
    field_nodes: List[Dict[str, Any]],
    civilian_reports: List[Dict[str, Any]],
    patient_zones: List[Dict[str, Any]],
) -> Tuple[float, float]:
    """Return centroid of all markers, falling back to HK central."""
    pts: List[Tuple[float, float]] = []
    for n in field_nodes:
        if "lat" in n and "lon" in n:
            pts.append((n["lat"], n["lon"]))
    for r in civilian_reports:
        if not r.get("acknowledged"):
            pts.append((r["lat"], r["lon"]))
    for p in patient_zones:
        if "lat" in p and "lon" in p:
            pts.append((p["lat"], p["lon"]))

    if not pts:
        return DEFAULT_CENTRE
    return (
        sum(p[0] for p in pts) / len(pts),
        sum(p[1] for p in pts) / len(pts),
    )


def _folium_color_from_severity(sev: str) -> str:
    return {
        "critical": "red",
        "high":     "orange",
        "moderate": "beige",
        "info":     "blue",
    }.get(sev.lower(), "gray")


def _triage_tag_color(tag: str) -> str:
    return {
        "RED":    "#dc2626",
        "YELLOW": "#eab308",
        "GREEN":  "#16a34a",
        "BLACK":  "#000000",
    }.get(tag.upper(), "#6b7280")


def _fallback_text(
    field_nodes: List[Dict[str, Any]],
    civilian_reports: List[Dict[str, Any]],
    patient_zones: List[Dict[str, Any]],
) -> str:
    """Plain HTML fallback when Folium isn't installed."""
    parts = ["<div style='font-family:sans-serif'>"]
    parts.append("<p><i>Folium not installed — install for live map. "
                 "Showing list view:</i></p>")
    parts.append(f"<h3>Field nodes ({len(field_nodes)})</h3><ul>")
    for n in field_nodes:
        parts.append(
            f"<li>{n.get('name', n['node_id'])} @ "
            f"{n['lat']:.4f}, {n['lon']:.4f}  "
            f"(RSSI {n.get('rssi','?')}, last seen {n.get('age_s','?')}s)</li>"
        )
    parts.append("</ul>")
    parts.append(f"<h3>Civilian distress ({len(civilian_reports)})</h3><ul>")
    for r in civilian_reports:
        if r.get("acknowledged"):
            continue
        parts.append(
            f"<li>[{r.get('severity_hint','?')}] "
            f"@ {r['lat']:.4f}, {r['lon']:.4f} — "
            f"{r.get('summary_en','')[:80]}</li>"
        )
    parts.append("</ul>")
    parts.append(f"<h3>Patient zones ({len(patient_zones)})</h3><ul>")
    for p in patient_zones:
        parts.append(
            f"<li>{p.get('patient_id','?')} [{p.get('tag','?')}] "
            f"@ {p['lat']:.4f}, {p['lon']:.4f}</li>"
        )
    parts.append("</ul></div>")
    return "".join(parts)
