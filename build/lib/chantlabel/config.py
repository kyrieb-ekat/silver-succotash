"""Pipeline parameters.

All geometric thresholds are expressed in units of the staff-line spacing (``sp``),
measured automatically on each image. The working image is rescaled so that the
spacing is close to ``target_spacing_px``; the pixel constants below that are not
written as fractions of ``sp`` assume that working scale.
"""
from dataclasses import dataclass, asdict


@dataclass
class Config:
    # --- working scale
    target_spacing_px: float = 50.0       # staff-line spacing in the working image
    working_scale: float = 0.0            # >0: use this fixed full-res -> working scale instead

    # --- staff lines
    staff_color: str = "red"              # "red" (red ruling) or "ink" (dark ruling, experimental)
    lines_per_staff: int = 4
    red_a_threshold: float = 140.0        # Lab a* above this counts as red
    red_a_range: float = 30.0
    strip_width_sp: float = 2.4           # vertical strip width for line tracking
    stave_gap_sp: float = 2.3             # consecutive lines further apart than this start a new staff

    # --- ink
    ink_threshold: int = 100              # 0..255 on the ink map
    head_open_px: int = 13                # opening kernel that removes stems/hairlines (working px)
    head_peak_min_dt: float = 6.5         # min distance-transform value of a head centre (working px)
    head_peak_min_dist: int = 11

    # --- staff band where note heads may sit (relative to top/bottom line)
    band_above_sp: float = 0.78           # heads may sit up to this far above the top line
    band_below_min_sp: float = 0.55       # at least this far below the bottom line ...
    band_below_text_margin_sp: float = 0.12   # ... or up to the measured text top minus this
    text_reach_sp: float = 0.95           # a blob reaching this far below the bottom line is text
    tall_blob_sp: float = 1.25            # solid blobs taller than this are initials/text strokes
    tall_blob_fill: float = 0.5

    # --- neume grouping
    stack_dx_sp: float = 0.25             # heads closer than this horizontally form a column (pes)
    group_gap_sp: float = 0.72            # split groups where heads are further apart than this
    climacus_dx_sp: tuple = (0.2, 0.8)
    duplicate_dx_sp: float = 0.62         # two peaks on one wide head
    virga_tail_sp: float = 0.45           # tail longer than this below the head -> virga

    # --- clefs
    auto_clefs: bool = True               # guess a C clef at the start of every staff
    clef_drop_rx_sp: float = 0.55
    clef_drop_ry_sp: float = 1.4

    # --- outputs
    viewer_tile: int = 2048
    jpeg_quality: int = 82

    def to_dict(self):
        return asdict(self)
