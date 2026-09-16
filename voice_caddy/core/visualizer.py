from __future__ import annotations

import plotly.graph_objects as go
from core.schemas import HoleData, Shot, LieType, ShotResult


class GolfHoleVisualizer:
    """
    Generates clean 2D Schematic Shot Trajectory Maps for each hole in Voice Caddy.
    Includes Ideal Target Landing Zone indicators comparing where the player should have landed vs where they landed.
    """

    @classmethod
    def create_hole_trajectory_map(cls, hole: HoleData) -> go.Figure:
        fig = go.Figure()

        # 1. Draw Stylized Hole Zones (Tee -> Fairway -> Green)
        # Background Fairway Corridor
        fig.add_shape(
            type="rect",
            x0=-25, y0=20, x1=25, y1=80,
            fillcolor="rgba(39, 174, 96, 0.15)",
            line=dict(color="#27AE60", width=1, dash="dash"),
        )
        # Green Zone at top
        fig.add_shape(
            type="path",
            path="M -15,85 Q 0,105 15,85 Q 20,75 0,78 Q -20,75 -15,85 Z",
            fillcolor="rgba(46, 204, 113, 0.4)",
            line=dict(color="#2ECC71", width=2),
        )

        # Draw Ideal Target Landing Ellipse (Gold Zone)
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

        # Flag Pin Position
        fig.add_trace(go.Scatter(
            x=[0], y=[92],
            mode="markers+text",
            marker=dict(symbol="triangle-up", size=14, color="#E74C3C"),
            text=["⛳ Buca"],
            textposition="top center",
            name="Bandiera",
            hoverinfo="skip"
        ))

        # Tee Box Position
        fig.add_trace(go.Scatter(
            x=[0], y=[0],
            mode="markers+text",
            marker=dict(symbol="square", size=12, color="#F1C40F"),
            text=["🏌️ Tee"],
            textposition="bottom center",
            name="Partenza",
            hoverinfo="skip"
        ))

        # 2. Map Shots to Coordinates based on qualitative data
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

        # 3. Draw Trajectory Vectors
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

        # 4. Styling Layout
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
