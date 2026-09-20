from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Optional, Dict, Tuple
from PIL import Image
import plotly.graph_objects as go
from core.schemas import HoleData, LieType


# Calibrated coordinates for Conero Golf Club (18 holes, image resolution 230x240)
# (x, y) coordinates in pixel space (where (0,0) is top-left, x: 0->230, y: 0->240)
CONERO_HOLE_COORDINATES: Dict[int, Dict[str, Tuple[int, int]]] = {
    1: {"tee": (64, 213), "green": (64, 23), "apex": (66, 115)},
    2: {"tee": (68, 216), "green": (66, 27), "apex": (67, 120)},
    3: {"tee": (58, 222), "green": (69, 32), "apex": (62, 125)},
    4: {"tee": (82, 197), "green": (57, 43), "apex": (70, 120)},
    5: {"tee": (36, 209), "green": (74, 46), "apex": (55, 120)},
    6: {"tee": (103, 183), "green": (85, 42), "apex": (94, 110)},
    7: {"tee": (72, 216), "green": (67, 34), "apex": (70, 125)},
    8: {"tee": (36, 219), "green": (42, 29), "apex": (39, 120)},
    9: {"tee": (44, 223), "green": (70, 54), "apex": (55, 135)},
    10: {"tee": (65, 215), "green": (40, 33), "apex": (52, 120)},
    11: {"tee": (106, 194), "green": (72, 38), "apex": (88, 115)},
    12: {"tee": (65, 215), "green": (85, 41), "apex": (75, 125)},
    13: {"tee": (58, 189), "green": (62, 37), "apex": (60, 110)},
    14: {"tee": (36, 196), "green": (59, 41), "apex": (48, 115)},
    15: {"tee": (41, 213), "green": (41, 47), "apex": (41, 130)},
    16: {"tee": (70, 211), "green": (83, 51), "apex": (76, 130)},
    17: {"tee": (58, 215), "green": (51, 29), "apex": (54, 120)},
    18: {"tee": (55, 218), "green": (91, 34), "apex": (70, 125)},
}


class GolfHoleVisualizer:
    """
    Generates high-precision 2D Shot Trajectory Maps for Voice Caddy.
    Supports authentic course hole drawings (Conero Golf Club, Torrenova, etc.)
    with calibrated vector shot overlays, Target Landing Zone indicators, and
    automatic fallback to schematic 2D corridor models.
    """

    @classmethod
    def find_hole_image(cls, course_id: Optional[str], hole_number: int) -> Optional[Path]:
        """Locates the authentic course drawing image file if available."""
        if not course_id:
            return None

        clean_id = str(course_id).strip().lower()
        search_dirs = [
            Path(__file__).resolve().parent.parent / "assets" / "courses" / clean_id,
            Path("voice_caddy") / "assets" / "courses" / clean_id,
            Path("assets") / "courses" / clean_id,
        ]
        extensions = ["png", "jpg", "jpeg", "webp", "gif"]
        for s_dir in search_dirs:
            if not s_dir.exists():
                continue
            for ext in extensions:
                img_p = s_dir / f"hole_{hole_number}.{ext}"
                if img_p.is_file():
                    return img_p
        return None

    @classmethod
    def create_hole_trajectory_map(
        cls,
        hole: HoleData,
        course_id: Optional[str] = None
    ) -> go.Figure:
        """
        Builds the shot trajectory visualization figure.
        Uses authentic hole map drawings if present for the course,
        otherwise falls back to the clean schematic corridor.
        """
        img_path = cls.find_hole_image(course_id, hole.hole_number)
        if img_path:
            try:
                return cls._create_authentic_hole_map(hole, course_id, img_path)
            except Exception:
                # Safe fallback in case of corrupted image or loading error
                pass

        return cls._create_schematic_fallback(hole)

    @classmethod
    def _create_authentic_hole_map(
        cls,
        hole: HoleData,
        course_id: Optional[str],
        img_path: Path
    ) -> go.Figure:
        """Renders authentic course drawing with calibrated trajectory overlays."""
        with Image.open(img_path) as im:
            im_rgba = im.convert("RGBA")
            w, h = im_rgba.size
            buf = io.BytesIO()
            im_rgba.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        fig = go.Figure()

        # 1. Background Course Drawing
        fig.add_layout_image(
            source=f"data:image/png;base64,{img_b64}",
            xref="x",
            yref="y",
            x=0,
            y=0,
            sizex=w,
            sizey=h,
            xanchor="left",
            yanchor="top",
            sizing="stretch",
            layer="below"
        )

        # 2. Coordinate Calibration
        clean_id = (course_id or "").lower()
        if "conero" in clean_id and hole.hole_number in CONERO_HOLE_COORDINATES:
            calib = CONERO_HOLE_COORDINATES[hole.hole_number]
            tee_x, tee_y = calib["tee"]
            green_x, green_y = calib["green"]
            apex_x, apex_y = calib.get("apex", ((tee_x + green_x) // 2, (tee_y + green_y) // 2))
        else:
            tee_x, tee_y = int(w * 0.28), int(h * 0.89)
            green_x, green_y = int(w * 0.32), int(h * 0.15)
            apex_x, apex_y = (tee_x + green_x) // 2, (tee_y + green_y) // 2

        # 3. Trajectory Points Generation
        x_coords = [tee_x]
        y_coords = [tee_y]
        hover_texts = ["<b>🏌️ Tee di Partenza</b>"]
        point_colors = ["#F59E0B"]  # Amber gold

        long_shots = [s for s in hole.shots if s.lie != LieType.GREEN]
        putt_shots = [s for s in hole.shots if s.lie == LieType.GREEN]
        num_long = max(len(long_shots), 1)

        for i, s in enumerate(long_shots):
            t = (i + 1) / (num_long + 1)
            # Quadratic Bezier along fairway corridor
            base_x = (1 - t)**2 * tee_x + 2 * (1 - t) * t * apex_x + t**2 * green_x
            base_y = (1 - t)**2 * tee_y + 2 * (1 - t) * t * apex_y + t**2 * green_y

            res_str = s.result.value if hasattr(s.result, 'value') else str(s.result)
            x_offset = 0
            if res_str in ("slice", "push", "miss_right"):
                x_offset = 14
            elif res_str in ("hook", "pull", "miss_left"):
                x_offset = -14
            elif res_str in ("bunker", "short"):
                x_offset = 8 if (i % 2 == 0) else -8

            shot_x = max(10, min(w - 10, base_x + x_offset))
            shot_y = max(10, min(h - 10, base_y))

            x_coords.append(shot_x)
            y_coords.append(shot_y)

            dist_str = f"{int(s.distance_meters)}m" if s.distance_meters else "N/D"
            club_str = s.club or "Bastone N/D"
            notes_str = f"<br><i>Note: {s.notes}</i>" if s.notes else ""
            lie_str = s.lie.value if hasattr(s.lie, 'value') else str(s.lie)

            hover_texts.append(
                f"<b>Colpo {s.shot_index}: {club_str}</b><br>"
                f"📏 Distanza: {dist_str}<br>"
                f"📍 Lie: {lie_str.upper()}<br>"
                f"🎯 Esito: {res_str.upper()}{notes_str}"
            )

            if res_str in ("fairway", "good", "green"):
                point_colors.append("#10B981")  # Emerald
            elif res_str in ("slice", "hook", "push", "pull", "miss_left", "miss_right", "bunker", "water"):
                point_colors.append("#EF4444")  # Coral red
            else:
                point_colors.append("#00D2FF")  # Cyan

        if putt_shots:
            x_coords.append(green_x)
            y_coords.append(green_y)
            hover_texts.append(f"<b>⛳ Green: {len(putt_shots)} Putt effettuati</b> (Score Buca: {hole.score})")
            point_colors.append("#10B981")

        # 4. Trajectory Flight Vectors
        for k in range(len(x_coords) - 1):
            is_putt_line = (k == len(x_coords) - 2) and (len(putt_shots) > 0)
            vector_color = "#F59E0B" if is_putt_line else "#00D2FF"
            dash_style = "dot" if is_putt_line else "solid"

            fig.add_trace(go.Scatter(
                x=[x_coords[k], x_coords[k + 1]],
                y=[y_coords[k], y_coords[k + 1]],
                mode="lines",
                line=dict(color=vector_color, width=3.5, dash=dash_style),
                showlegend=False,
                hoverinfo="skip"
            ))

        # 5. Glowing Shot Markers
        fig.add_trace(go.Scatter(
            x=x_coords,
            y=y_coords,
            mode="markers",
            marker=dict(
                size=11,
                color=point_colors,
                line=dict(color="#FFFFFF", width=2),
                symbol="circle"
            ),
            text=hover_texts,
            hoverinfo="text",
            showlegend=False
        ))

        # 6. Target Ideale Indicator
        if hole.target_landing_analysis:
            t_target = 0.52 if len(long_shots) > 1 else 0.42
            target_x = (1 - t_target)**2 * tee_x + 2 * (1 - t_target) * t_target * apex_x + t_target**2 * green_x
            target_y = (1 - t_target)**2 * tee_y + 2 * (1 - t_target) * t_target * apex_y + t_target**2 * green_y
            fig.add_shape(
                type="circle",
                xref="x", yref="y",
                x0=target_x - 11, y0=target_y - 11,
                x1=target_x + 11, y1=target_y + 11,
                fillcolor="rgba(245, 158, 11, 0.25)",
                line=dict(color="#F59E0B", width=2, dash="dot"),
            )
            fig.add_trace(go.Scatter(
                x=[target_x], y=[target_y],
                mode="text",
                text=["🎯 Target"],
                textposition="top center",
                textfont=dict(color="#D97706", size=10, family="Arial Black"),
                showlegend=False,
                hoverinfo="text",
                hovertext=[f"🎯 Target Ideale: {hole.target_landing_analysis.ideal_target_zone}"]
            ))

        # 7. Pin / Flag Marker
        fig.add_trace(go.Scatter(
            x=[green_x],
            y=[green_y],
            mode="markers+text",
            marker=dict(symbol="triangle-up", size=14, color="#EF4444", line=dict(color="#FFFFFF", width=1.5)),
            text=["⛳"],
            textposition="top center",
            showlegend=False,
            hoverinfo="text",
            hovertext=[f"<b>⛳ Pin / Green Buca {hole.hole_number}</b>"]
        ))

        # 8. Styling & Viewport
        fig.update_xaxes(range=[0, w], showgrid=False, zeroline=False, visible=False, fixedrange=True)
        fig.update_yaxes(range=[h, 0], showgrid=False, zeroline=False, visible=False, fixedrange=True)
        fig.update_layout(
            title=dict(
                text=f"🗺️ Disegno Ufficiale — Buca {hole.hole_number} (Par {hole.par})",
                font=dict(size=13, color="#E2E8F0")
            ),
            height=420,
            margin=dict(l=5, r=5, t=35, b=5),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False
        )
        return fig

    @classmethod
    def _create_schematic_fallback(cls, hole: HoleData) -> go.Figure:
        """Schematic fallback map when no authentic image is present."""
        fig = go.Figure()

        # Stylized Fairway
        fig.add_shape(
            type="rect",
            x0=-25, y0=20, x1=25, y1=80,
            fillcolor="rgba(39, 174, 96, 0.15)",
            line=dict(color="#27AE60", width=1, dash="dash"),
        )
        # Green Zone
        fig.add_shape(
            type="path",
            path="M -15,85 Q 0,105 15,85 Q 20,75 0,78 Q -20,75 -15,85 Z",
            fillcolor="rgba(46, 204, 113, 0.4)",
            line=dict(color="#2ECC71", width=2),
        )

        # Target Landing Area
        fig.add_shape(
            type="circle",
            xref="x", yref="y",
            x0=-10, y0=45, x1=10, y1=65,
            fillcolor="rgba(241, 196, 15, 0.25)",
            line=dict(color="#F1C40F", width=2, dash="dot"),
        )
        fig.add_trace(go.Scatter(
            x=[0], y=[55],
            mode="text",
            text=["🎯 Target Ideale"],
            textposition="middle center",
            textfont=dict(color="#F39C12", size=10),
            name="Target Ideale",
            hoverinfo="skip"
        ))

        # Flag Pin
        fig.add_trace(go.Scatter(
            x=[0], y=[92],
            mode="markers+text",
            marker=dict(symbol="triangle-up", size=14, color="#E74C3C"),
            text=["⛳ Buca"],
            textposition="top center",
            name="Bandiera",
            hoverinfo="skip"
        ))

        # Tee Box
        fig.add_trace(go.Scatter(
            x=[0], y=[0],
            mode="markers+text",
            marker=dict(symbol="square", size=12, color="#F1C40F"),
            text=["🏌️ Tee"],
            textposition="bottom center",
            name="Partenza",
            hoverinfo="skip"
        ))

        # Shots
        x_coords = [0]
        y_coords = [0]
        hover_texts = ["<b>Partenza dal Tee</b>"]

        long_shots = [s for s in hole.shots if s.lie != LieType.GREEN]
        putt_shots = [s for s in hole.shots if s.lie == LieType.GREEN]
        num_long = max(len(long_shots), 1)

        for i, s in enumerate(long_shots):
            progress_y = int(25 + (i + 1) * (60.0 / num_long))
            if progress_y > 88:
                progress_y = 88

            res_str = s.result.value if hasattr(s.result, 'value') else str(s.result)
            x_offset = 0
            if res_str in ("slice", "push", "miss_right"):
                x_offset = 18
            elif res_str in ("hook", "pull", "miss_left"):
                x_offset = -18
            elif res_str == "fairway":
                x_offset = 0
            elif res_str in ("green", "good"):
                x_offset = 2 if (i % 2 == 0) else -2
            elif res_str in ("bunker", "short"):
                x_offset = 10 if (i % 2 == 0) else -10

            x_coords.append(x_offset)
            y_coords.append(progress_y)

            dist_str = f"{int(s.distance_meters)}m" if s.distance_meters else "N/D"
            club_str = s.club or "Bastone N/D"
            notes_str = f"<br><i>Note: {s.notes}</i>" if s.notes else ""

            hover_texts.append(
                f"<b>Colpo {s.shot_index}: {club_str}</b><br>"
                f"Distanza: {dist_str}<br>"
                f"Posizione: {s.lie.value if hasattr(s.lie, 'value') else s.lie}<br>"
                f"Esito: {res_str.upper()}{notes_str}"
            )

        if putt_shots:
            x_coords.append(0)
            y_coords.append(92)
            hover_texts.append(f"<b>Green: {len(putt_shots)} Putt effettuati</b> (Score: {hole.score})")

        for k in range(len(x_coords) - 1):
            line_color = "#3498DB" if k < len(long_shots) else "#E74C3C"
            fig.add_trace(go.Scatter(
                x=[x_coords[k], x_coords[k+1]],
                y=[y_coords[k], y_coords[k+1]],
                mode="lines+markers",
                line=dict(color=line_color, width=3, dash="solid" if k < len(long_shots) else "dot"),
                marker=dict(size=8, color="#FFFFFF", line=dict(color=line_color, width=2)),
                showlegend=False,
                hoverinfo="text",
                hovertext=[hover_texts[k], hover_texts[k+1]]
            ))

        h_num = hole.hole_number if hasattr(hole, 'hole_number') else getattr(hole, 'number', 1)
        fig.update_layout(
            title=dict(text=f"Mappa Tattica Vettoriale — Buca {h_num} (Par {hole.par})", font=dict(size=14)),
            xaxis=dict(visible=False, range=[-35, 35]),
            yaxis=dict(visible=False, range=[-10, 110]),
            height=380,
            margin=dict(l=10, r=10, t=40, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False
        )
        return fig
