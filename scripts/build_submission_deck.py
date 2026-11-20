"""
CareBridge Future Health Digital Innovation Challenge Submission Deck Generator
Generates AiMavericks_CareBridge_Submission.pptx adhering strictly to challenge rules.
"""

import os
import re
import fitz  # PyMuPDF
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor

# Dimensions (16:9 widescreen standard)
SLIDE_WIDTH = Inches(13.333333)
SLIDE_HEIGHT = Inches(7.5)

# Color Palette
COLOR_BG_LIGHT = RGBColor(250, 248, 245)
COLOR_WHITE = RGBColor(255, 255, 255)
COLOR_NAVY_DARK = RGBColor(30, 41, 59)        # #1E293B
COLOR_TEXT_MAIN = RGBColor(30, 41, 59)        # #1E293B
COLOR_TEXT_MUTED = RGBColor(100, 116, 139)    # #64748B
COLOR_BORDER = RGBColor(203, 213, 225)        # #CBD5E1
COLOR_BORDER_STRONG = RGBColor(148, 163, 184) # #94A3B8

COLOR_PRIMARY_BLUE = RGBColor(30, 58, 138)   # #1E3A8A
COLOR_ACCENT_BLUE = RGBColor(37, 99, 235)    # #2563EB
COLOR_ACCENT_TEAL = RGBColor(13, 148, 136)   # #0D9488
COLOR_ACCENT_GREEN = RGBColor(22, 101, 52)   # #166534
COLOR_ACCENT_AMBER = RGBColor(180, 83, 9)    # #B45309
COLOR_RED_FILL = RGBColor(220, 38, 38)       # #DC2626 - Strictly for [FILL: ...] markers
COLOR_BOX_BG = RGBColor(248, 250, 252)       # #F8FAFC
COLOR_HEADER_BG = RGBColor(241, 245, 249)    # #F1F5F9


def add_text_with_fill_highlight(paragraph, text, default_color=COLOR_TEXT_MAIN, default_size=Pt(14), is_bold=False):
    """Parses text containing [FILL: ...] markers and renders the fill markers in bold red."""
    tokens = re.split(r'(\[FILL:[^\]]*\]|\[FILL\])', text)
    for token in tokens:
        if not token:
            continue
        run = paragraph.add_run()
        run.text = token
        run.font.size = default_size
        run.font.name = 'Arial'
        if token.startswith('[FILL'):
            run.font.color.rgb = COLOR_RED_FILL
            run.font.bold = True
        else:
            run.font.color.rgb = default_color
            run.font.bold = is_bold


def create_table(slide, left, top, width, height, headers, rows, col_widths=None, font_size=Pt(13), header_bg=COLOR_HEADER_BG):
    """Creates a styled native PowerPoint table."""
    num_rows = len(rows) + 1
    num_cols = len(headers)
    table_shape = slide.shapes.add_table(num_rows, num_cols, left, top, width, height)
    table = table_shape.table

    if col_widths and len(col_widths) == num_cols:
        for idx, w in enumerate(col_widths):
            table.columns[idx].width = w

    # Header Row
    for idx, header in enumerate(headers):
        cell = table.cell(0, idx)
        cell.fill.solid()
        cell.fill.fore_color.rgb = header_bg
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = header
        run.font.bold = True
        run.font.size = font_size
        run.font.name = 'Arial'
        run.font.color.rgb = COLOR_NAVY_DARK

    # Data Rows
    for r_idx, row_data in enumerate(rows):
        row_num = r_idx + 1
        for c_idx, cell_value in enumerate(row_data):
            cell = table.cell(row_num, c_idx)
            cell.fill.solid()
            # Alternate row background
            if r_idx % 2 == 1:
                cell.fill.fore_color.rgb = COLOR_BOX_BG
            else:
                cell.fill.fore_color.rgb = COLOR_WHITE
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT
            add_text_with_fill_highlight(p, cell_value, default_color=COLOR_TEXT_MAIN, default_size=font_size)

    return table_shape


def render_template_backgrounds(pdf_path, output_dir):
    """Renders all 16 template pages from the PDF into high-resolution PNG backgrounds."""
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    bg_paths = []
    print(f"Rendering {len(doc)} template pages to high-res PNG at 192 DPI...")
    for i in range(len(doc)):
        page = doc[i]
        pix = page.get_pixmap(dpi=192)  # 192 dpi produces 1920x1080 from 720x405
        path = os.path.join(output_dir, f"template_slide_{i+1:02d}.png")
        pix.save(path)
        bg_paths.append(path)
    return bg_paths


def build_presentation(bg_images):
    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT
    blank_layout = prs.slide_layouts[6]

    # Helper to add background
    def add_slide_with_bg(slide_num):
        slide = prs.slides.add_slide(blank_layout)
        bg_img = bg_images[slide_num - 1]
        slide.shapes.add_picture(bg_img, Inches(0), Inches(0), SLIDE_WIDTH, SLIDE_HEIGHT)
        return slide

    # =========================================================================
    # SLIDE 1: COVER
    # =========================================================================
    print("Building Slide 1: Cover...")
    s1 = add_slide_with_bg(1)
    
    # Clean white mask to completely eliminate ghost/double printing from the template PDF text
    mask_s1 = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(4.35), Inches(12.2), Inches(2.6))
    mask_s1.fill.solid()
    mask_s1.fill.fore_color.rgb = COLOR_WHITE
    mask_s1.line.fill.background()

    tx_box = s1.shapes.add_textbox(Inches(0.77), Inches(4.45), Inches(11.8), Inches(2.4))
    tf = tx_box.text_frame
    tf.word_wrap = True
    
    # Team Name value
    p1 = tf.paragraphs[0]
    p1.space_after = Pt(10)
    r1 = p1.add_run()
    r1.text = "Team Name:  "
    r1.font.bold = True
    r1.font.size = Pt(22)
    r1.font.color.rgb = COLOR_NAVY_DARK
    r1_val = p1.add_run()
    r1_val.text = "Ai_Mavericks"
    r1_val.font.bold = True
    r1_val.font.size = Pt(22)
    r1_val.font.color.rgb = COLOR_ACCENT_BLUE

    # Team Size value
    p2 = tf.add_paragraph()
    p2.space_after = Pt(10)
    r2 = p2.add_run()
    r2.text = "Team Size:  "
    r2.font.bold = True
    r2.font.size = Pt(22)
    r2.font.color.rgb = COLOR_NAVY_DARK
    r2_val = p2.add_run()
    r2_val.text = "3"
    r2_val.font.bold = True
    r2_val.font.size = Pt(22)
    r2_val.font.color.rgb = COLOR_TEXT_MAIN

    # Problem Statement value
    p3 = tf.add_paragraph()
    p3.space_after = Pt(14)
    r3 = p3.add_run()
    r3.text = "Problem Statement:  "
    r3.font.bold = True
    r3.font.size = Pt(22)
    r3.font.color.rgb = COLOR_NAVY_DARK
    r3_val = p3.add_run()
    r3_val.text = "Closing the Screening-to-Care Loop"
    r3_val.font.bold = True
    r3_val.font.size = Pt(22)
    r3_val.font.color.rgb = COLOR_ACCENT_TEAL

    # Small subtitle line under it
    p4 = tf.add_paragraph()
    r4 = p4.add_run()
    r4.text = '“CareBridge: an AI care-coordination platform that makes sure no patient is lost between screening and treatment.”'
    r4.font.size = Pt(16)
    r4.font.italic = True
    r4.font.color.rgb = COLOR_TEXT_MUTED

    # =========================================================================
    # SLIDE 2: TEAM MEMBERS
    # =========================================================================
    print("Building Slide 2: Team Members...")
    s2 = add_slide_with_bg(2)
    
    # White background card to mask the template PDF table outlines cleanly
    mask_s2 = s2.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.35), Inches(2.15), Inches(12.75), Inches(3.85))
    mask_s2.fill.solid()
    mask_s2.fill.fore_color.rgb = COLOR_WHITE
    mask_s2.line.fill.solid()
    mask_s2.line.fill.fore_color.rgb = COLOR_WHITE

    # Fill the existing table structure (rows 1-3 filled, rows 4-5 blank)
    headers_s2 = ["S.No", "Name", "Country", "Role", "Organization", "Age confirmation"]
    rows_s2 = [
        ["1", "Sanjay S", "India", "Software Engineer", "Individual", "23"],
        ["2", "Hari Haran S", "India", "Freelancer", "Individual", "22"],
        ["3", "Vasanthan S R", "India", "Software Engineer", "Individual", "23"],
        ["4", "", "", "", "", ""],
        ["5", "", "", "", "", ""]
    ]
    col_widths_s2 = [Inches(1.0), Inches(2.8), Inches(1.8), Inches(2.6), Inches(2.4), Inches(1.75)]
    create_table(s2, Inches(0.5), Inches(2.25), Inches(12.35), Inches(3.6), headers_s2, rows_s2, col_widths_s2, font_size=Pt(14))

    # =========================================================================
    # SLIDE 3: TEAM CAPABILITY SUMMARY (max 1,000 chars)
    # =========================================================================
    print("Building Slide 3: Team Capability Summary...")
    s3 = add_slide_with_bg(3)
    summary_text = (
        "Ai_Mavericks is a three-member team from India building CareBridge, a working multi-role "
        "care-coordination platform. Our stack: FastAPI, PostgreSQL 17, Next.js/React, LangGraph multi-agent "
        "orchestration, FHIR R4 and SSE notifications. Our strengths are agentic AI workflows with role-based "
        "authorization, event-driven backend design, healthcare interoperability and reliability engineering. "
        "We are hardening the platform with evidence-based lifecycle transitions, a transactional outbox and "
        "end-to-end traceability, so every AI action is backed by persisted records. We use synthetic data "
        "only, and clinical decisions always stay with authorized doctors."
    )
    assert len(summary_text) <= 1000, f"Slide 3 text exceeds 1,000 characters! Current: {len(summary_text)}"
    print(f"Slide 3 verified character count: {len(summary_text)} characters (<= 1,000 limit)")

    # Prominent Card Container
    card_shape = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.65), Inches(2.1), Inches(12.0), Inches(3.6))
    card_shape.fill.solid()
    card_shape.fill.fore_color.rgb = COLOR_BOX_BG
    card_shape.line.color.rgb = COLOR_BORDER
    card_shape.line.width = Pt(1.5)

    tf3 = card_shape.text_frame
    tf3.word_wrap = True
    tf3.margin_left = Inches(0.45)
    tf3.margin_right = Inches(0.45)
    tf3.margin_top = Inches(0.45)
    tf3.margin_bottom = Inches(0.45)

    p3_body = tf3.paragraphs[0]
    p3_body.alignment = PP_ALIGN.LEFT
    p3_body.line_spacing = 1.3
    r3_body = p3_body.add_run()
    r3_body.text = summary_text
    r3_body.font.size = Pt(17)
    r3_body.font.name = 'Arial'
    r3_body.font.color.rgb = COLOR_TEXT_MAIN

    # Highlights strip at the bottom of the card
    highlights_box = s3.shapes.add_textbox(Inches(0.65), Inches(5.9), Inches(12.0), Inches(0.8))
    tf_h = highlights_box.text_frame
    p_h = tf_h.paragraphs[0]
    p_h.alignment = PP_ALIGN.CENTER
    r_h = p_h.add_run()
    r_h.text = "Core Competencies:  Agentic AI Orchestration  •  Role-Based Authorization  •  FHIR R4 Interoperability  •  Transactional Outbox & SSE"
    r_h.font.bold = True
    r_h.font.size = Pt(14)
    r_h.font.color.rgb = COLOR_PRIMARY_BLUE

    # =========================================================================
    # SLIDE 4: ARCHITECTURE OR WORKFLOW DIAGRAM
    # NATIVE shapes and connectors, template colors, >= 12 pt font.
    # =========================================================================
    print("Building Slide 4: Architecture Diagram (Native Shapes)...")
    s4 = add_slide_with_bg(4)

    # Right side vertical strip: "14-stage lifecycle: stages complete only from persisted evidence"
    strip_box = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(10.55), Inches(1.85), Inches(2.25), Inches(4.10))
    strip_box.fill.solid()
    strip_box.fill.fore_color.rgb = RGBColor(241, 245, 249)
    strip_box.line.color.rgb = COLOR_ACCENT_TEAL
    strip_box.line.width = Pt(1.5)
    tf_strip = strip_box.text_frame
    tf_strip.word_wrap = True
    tf_strip.margin_left = Inches(0.12)
    tf_strip.margin_right = Inches(0.12)
    tf_strip.margin_top = Inches(0.12)
    tf_strip.margin_bottom = Inches(0.12)
    
    p_st = tf_strip.paragraphs[0]
    p_st.alignment = PP_ALIGN.CENTER
    r_st = p_st.add_run()
    r_st.text = "14-Stage Lifecycle"
    r_st.font.bold = True
    r_st.font.size = Pt(12)
    r_st.font.color.rgb = COLOR_PRIMARY_BLUE

    p_st2 = tf_strip.add_paragraph()
    p_st2.alignment = PP_ALIGN.CENTER
    p_st2.space_after = Pt(4)
    r_st2 = p_st2.add_run()
    r_st2.text = "(Stages complete ONLY from persisted evidence)"
    r_st2.font.italic = True
    r_st2.font.size = Pt(9)
    r_st2.font.color.rgb = COLOR_TEXT_MUTED

    stages_list = [
        "1. Screening", "2. Result", "3. Patient Notification",
        "4. Patient Understanding", "5. Clinical Review", "6. Clinical Confirmation",
        "7. Referral", "8. Referral Acceptance", "9. Appointment",
        "10. Consultation", "11. Treatment Monitoring", "12. Follow-up",
        "13. Documentation", "14. Closure (Doctor sign-off only)"
    ]
    for st_text in stages_list:
        p_item = tf_strip.add_paragraph()
        p_item.alignment = PP_ALIGN.LEFT
        r_item = p_item.add_run()
        r_item.text = st_text
        r_item.font.size = Pt(8.5)
        if "14." in st_text:
            r_item.font.bold = True
            r_item.font.color.rgb = COLOR_ACCENT_AMBER
        else:
            r_item.font.color.rgb = COLOR_TEXT_MAIN

    # Main Architecture Canvas (Left side: x = 0.55 to 10.35, width = 9.8 in)
    diag_left = Inches(0.55)
    diag_width = Inches(9.8)

    # Helper for centered box
    def add_arch_box(y, h, text, bg_color=COLOR_BOX_BG, border_color=COLOR_BORDER, font_size=Pt(12), is_bold=True, text_color=COLOR_TEXT_MAIN):
        box = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, diag_left, y, diag_width, h)
        box.fill.solid()
        box.fill.fore_color.rgb = bg_color
        box.line.color.rgb = border_color
        box.line.width = Pt(1.2)
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = text
        r.font.bold = is_bold
        r.font.size = font_size
        r.font.color.rgb = text_color
        return box

    # Row 1: Three role boxes
    y_row1 = Inches(1.85)
    h_row1 = Inches(0.58)
    w_role = Inches(3.13)
    gap_role = Inches(0.2)
    roles = [
        ("PATIENT", "Next.js Dashboard + Multilingual AI Chat", COLOR_PRIMARY_BLUE),
        ("DOCTOR", "Next.js Dashboard + Clinical Review & Sign-Off", COLOR_ACCENT_TEAL),
        ("CARE_COORDINATOR", "Next.js Hub + Orders, Allocation & SLAs", COLOR_ACCENT_AMBER)
    ]
    for idx, (role_name, role_sub, color) in enumerate(roles):
        rx = diag_left + idx * (w_role + gap_role)
        rbox = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, rx, y_row1, w_role, h_row1)
        rbox.fill.solid()
        rbox.fill.fore_color.rgb = COLOR_WHITE
        rbox.line.color.rgb = color
        rbox.line.width = Pt(1.5)
        tf = rbox.text_frame
        tf.word_wrap = True
        p1 = tf.paragraphs[0]
        p1.alignment = PP_ALIGN.CENTER
        r1 = p1.add_run()
        r1.text = role_name + "\n"
        r1.font.bold = True
        r1.font.size = Pt(13)
        r1.font.color.rgb = color
        r2 = p1.add_run()
        r2.text = role_sub
        r2.font.size = Pt(10)
        r2.font.color.rgb = COLOR_TEXT_MUTED

    # Row 2: FastAPI + JWT auth + role detection
    y_row2 = Inches(2.52)
    add_arch_box(y_row2, Inches(0.42), "FastAPI  •  JWT Authentication  •  Role & Context Detection Guardrails",
                 bg_color=RGBColor(241, 245, 249), border_color=COLOR_BORDER_STRONG, font_size=Pt(12.5), text_color=COLOR_PRIMARY_BLUE)

    # Row 3: AI Supervisor (LangGraph): intent + role + context -> routes to:
    y_row3 = Inches(3.02)
    add_arch_box(y_row3, Inches(0.42), "AI Supervisor (LangGraph): Intent + Role + Clinical Context  →  Authorized Routing",
                 bg_color=RGBColor(238, 242, 255), border_color=COLOR_ACCENT_BLUE, font_size=Pt(12.5), text_color=COLOR_PRIMARY_BLUE)

    # Row 4: Six Agent Boxes
    y_row4 = Inches(3.52)
    h_row4 = Inches(0.68)
    agents = [
        ("Patient AI", "Intake &\nEducation"),
        ("Doctor AI\nSubgraph", "11-Node Clinical\nReview"),
        ("Care Coord\nAgent", "Orders, Doctors\n& SLA Tracking"),
        ("Recovery\nAgent", "No-Shows &\nBarriers"),
        ("Clinical Escalation\n(Rule-Based)", "Zero-LLM Safety\nRed Flags"),
        ("Doctor Review\nAgent", "Verification &\nClosure Gate")
    ]
    w_agent = Inches(1.52)
    gap_agent = Inches(0.13)
    for idx, (a_name, a_desc) in enumerate(agents):
        ax = diag_left + idx * (w_agent + gap_agent)
        abox = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, ax, y_row4, w_agent, h_row4)
        abox.fill.solid()
        abox.fill.fore_color.rgb = COLOR_BOX_BG
        abox.line.color.rgb = COLOR_ACCENT_TEAL if "Doctor" in a_name else COLOR_BORDER_STRONG
        abox.line.width = Pt(1.2)
        tf = abox.text_frame
        tf.word_wrap = True
        tf.margin_top = Inches(0.04)
        p1 = tf.paragraphs[0]
        p1.alignment = PP_ALIGN.CENTER
        r1 = p1.add_run()
        r1.text = a_name + "\n"
        r1.font.bold = True
        r1.font.size = Pt(10.5)
        r1.font.color.rgb = COLOR_NAVY_DARK
        r2 = p1.add_run()
        r2.text = a_desc
        r2.font.size = Pt(8.5)
        r2.font.color.rgb = COLOR_TEXT_MUTED

    # Row 5: Tool Registry
    y_row5 = Inches(4.28)
    add_arch_box(y_row5, Inches(0.42), "Tool Registry: Role-Permissioned, Schema-Validated Healthcare Tools (Pydantic)",
                 bg_color=RGBColor(240, 253, 250), border_color=COLOR_ACCENT_TEAL, font_size=Pt(12.5), text_color=COLOR_ACCENT_TEAL)

    # Row 6: Domain workflow services + single lifecycle transition service (evidence required)
    y_row6 = Inches(4.78)
    add_arch_box(y_row6, Inches(0.42), "Domain Workflow Services  +  Single Lifecycle Transition Service (Evidence Required)",
                 bg_color=RGBColor(254, 243, 199), border_color=COLOR_ACCENT_AMBER, font_size=Pt(12.5), text_color=COLOR_ACCENT_AMBER)

    # Row 7: PostgreSQL 17 + Side boxes
    y_row7 = Inches(5.28)
    h_row7 = Inches(0.58)
    # 4 columns in Row 7: Outbox (2.6 in), PostgreSQL 17 (3.4 in), FHIR R4 (1.8 in), Audit Log (1.6 in)
    r7_boxes = [
        ("Transactional Outbox\nWorker → SSE Notifications", Inches(2.6), RGBColor(238, 242, 255), COLOR_ACCENT_BLUE),
        ("PostgreSQL 17 Database\nSingle Source of Truth (Relational + Evidence)", Inches(3.3), RGBColor(241, 245, 249), COLOR_PRIMARY_BLUE),
        ("FHIR R4\nInteroperability", Inches(1.8), RGBColor(240, 253, 244), COLOR_ACCENT_GREEN),
        ("Audit & Trace\nTamper-Proof Log", Inches(1.7), RGBColor(254, 242, 242), COLOR_RED_FILL)
    ]
    cur_x = diag_left
    for text, w_b, bg, border in r7_boxes:
        bx = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cur_x, y_row7, w_b, h_row7)
        bx.fill.solid()
        bx.fill.fore_color.rgb = bg
        bx.line.color.rgb = border
        bx.line.width = Pt(1.2)
        tf = bx.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = text
        r.font.bold = True
        r.font.size = Pt(10.5)
        r.font.color.rgb = border
        cur_x += w_b + Inches(0.13)

    # Bottom caption - clean width spanning both columns cleanly, well above footer
    y_cap = Inches(6.05)
    cap_box = s4.shapes.add_shape(MSO_SHAPE.RECTANGLE, diag_left, y_cap, Inches(12.25), Inches(0.48))
    cap_box.fill.solid()
    cap_box.fill.fore_color.rgb = COLOR_NAVY_DARK
    cap_box.line.color.rgb = COLOR_NAVY_DARK
    tf_c = cap_box.text_frame
    p_c = tf_c.paragraphs[0]
    p_c.alignment = PP_ALIGN.CENTER
    r_c = p_c.add_run()
    r_c.text = "AI proposes  →  Workflow engine validates  →  Database records  →  Events notify  →  Dashboards show verified state"
    r_c.font.bold = True
    r_c.font.size = Pt(13.5)
    r_c.font.color.rgb = COLOR_WHITE

    # =========================================================================
    # SLIDE 5: TARGET USERS AND INTENDED OUTCOME
    # =========================================================================
    print("Building Slide 5: Target Users & Intended Outcome...")
    s5 = add_slide_with_bg(5)

    # 3 User Cards Side-by-Side
    card_w = Inches(3.85)
    card_h = Inches(3.6)
    card_y = Inches(1.9)
    gap_c = Inches(0.38)
    user_data = [
        ("PATIENTS", COLOR_PRIMARY_BLUE, [
            "Always know what has happened, what is pending, and who is responsible.",
            "Receive plain-language diagnostic report explanations in English, Arabic (RTL), and Spanish.",
            "Guided preparation for specialist visits with barrier assistance (transport, caregiver, anxiety)."
        ]),
        ("CARE COORDINATORS", COLOR_ACCENT_AMBER, [
            "Unified operational queue for new screening requirements, orders, and physician allocation.",
            "Active monitoring of referral delays and strict screening-to-consultation SLA deadlines.",
            "Automated recovery playbooks for missed appointments, no-shows, and overdue follow-ups."
        ]),
        ("DOCTORS", COLOR_ACCENT_TEAL, [
            "Focused clinical view limited strictly to their assigned cases and pending reviews.",
            "Structured pre-consultation summaries, referral reviews, and clinical decision support.",
            "Exclusive human sign-off authority required for clinical confirmation and final case closure."
        ])
    ]

    for idx, (title, color, bullets) in enumerate(user_data):
        cx = Inches(0.65) + idx * (card_w + gap_c)
        card = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, card_y, card_w, card_h)
        card.fill.solid()
        card.fill.fore_color.rgb = COLOR_WHITE
        card.line.color.rgb = color
        card.line.width = Pt(1.8)
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.25)
        tf.margin_right = Inches(0.25)
        tf.margin_top = Inches(0.25)

        # Title
        p_t = tf.paragraphs[0]
        p_t.space_after = Pt(12)
        r_t = p_t.add_run()
        r_t.text = title
        r_t.font.bold = True
        r_t.font.size = Pt(18)
        r_t.font.color.rgb = color

        # Bullets
        for b in bullets:
            p_b = tf.add_paragraph()
            p_b.space_after = Pt(10)
            p_b.level = 0
            r_dot = p_b.add_run()
            r_dot.text = "•  "
            r_dot.font.bold = True
            r_dot.font.size = Pt(14)
            r_dot.font.color.rgb = color
            r_txt = p_b.add_run()
            r_txt.text = b
            r_txt.font.size = Pt(14)
            r_txt.font.color.rgb = COLOR_TEXT_MAIN

    # Outcome Bar across the bottom
    outcome_box = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.65), Inches(5.75), Inches(12.0), Inches(0.95))
    outcome_box.fill.solid()
    outcome_box.fill.fore_color.rgb = RGBColor(240, 253, 250)
    outcome_box.line.color.rgb = COLOR_ACCENT_TEAL
    outcome_box.line.width = Pt(1.8)
    tf_o = outcome_box.text_frame
    tf_o.word_wrap = True
    tf_o.margin_left = Inches(0.3)
    tf_o.margin_right = Inches(0.3)
    tf_o.margin_top = Inches(0.12)

    p_ot = tf_o.paragraphs[0]
    p_ot.alignment = PP_ALIGN.CENTER
    r_ot = p_ot.add_run()
    r_ot.text = "INTENDED OUTCOME\n"
    r_ot.font.bold = True
    r_ot.font.size = Pt(13)
    r_ot.font.color.rgb = COLOR_ACCENT_TEAL
    r_ob = p_ot.add_run()
    r_ob.text = "“No patient lost between screening, result, specialist and follow-up: every handoff is a persisted task, every status is backed by evidence.”"
    r_ob.font.bold = True
    r_ob.font.size = Pt(15.5)
    r_ob.font.color.rgb = COLOR_NAVY_DARK

    # =========================================================================
    # SLIDE 6: HOW WILL SUCCESS BE MEASURED?
    # =========================================================================
    print("Building Slide 6: How Will Success Be Measured?...")
    s6 = add_slide_with_bg(6)

    headers_s6 = ["Metric", "Definition", "Target"]
    rows_s6 = [
        ["Handoff integrity", "Screening requirements that produce a coordinator task + notification", "100%"],
        ["Evidence integrity", "Lifecycle stages marked complete that have persisted evidence", "100%"],
        ["Notification durability", "Notifications delivered or dead-lettered with a record (none silently lost)", "100%"],
        ["Time to coordinator action", "Requirement created  →  screening order created", "[FILL: pilot target]"],
        ["Result understanding", "Reports explained to the patient within [FILL] of finalization", "[FILL]"],
        ["Loop closure", "Abnormal/required follow-ups reaching consultation or documented closure", "[FILL: baseline vs pilot]"],
        ["Missed-appointment recovery", "No-shows with a recovery task opened", "100%"]
    ]
    col_widths_s6 = [Inches(3.2), Inches(6.3), Inches(2.5)]
    create_table(s6, Inches(0.65), Inches(1.85), Inches(12.0), Inches(4.3), headers_s6, rows_s6, col_widths_s6, font_size=Pt(13.5))

    # Footnote
    fn_box = s6.shapes.add_textbox(Inches(0.65), Inches(6.35), Inches(12.0), Inches(0.5))
    tf_fn = fn_box.text_frame
    p_fn = tf_fn.paragraphs[0]
    r_fn = p_fn.add_run()
    r_fn.text = "* Footnote: Targets are design goals for a pilot, not results achieved."
    r_fn.font.italic = True
    r_fn.font.size = Pt(12)
    r_fn.font.color.rgb = COLOR_TEXT_MUTED

    # =========================================================================
    # SLIDE 7: EVIDENCE SUPPORTING THE APPROACH
    # =========================================================================
    print("Building Slide 7: Evidence Supporting the Approach...")
    s7 = add_slide_with_bg(7)

    col_w = Inches(5.85)
    col_h = Inches(4.4)
    col_y = Inches(1.85)

    # Left Column: Problem Evidence
    left_card = s7.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.65), col_y, col_w, col_h)
    left_card.fill.solid()
    left_card.fill.fore_color.rgb = COLOR_WHITE
    left_card.line.color.rgb = COLOR_BORDER
    left_card.line.width = Pt(1.5)
    tf_l = left_card.text_frame
    tf_l.word_wrap = True
    tf_l.margin_left = Inches(0.3)
    tf_l.margin_right = Inches(0.3)
    tf_l.margin_top = Inches(0.25)

    p_lt = tf_l.paragraphs[0]
    p_lt.space_after = Pt(14)
    r_lt = p_lt.add_run()
    r_lt.text = "Problem Evidence"
    r_lt.font.bold = True
    r_lt.font.size = Pt(18)
    r_lt.font.color.rgb = COLOR_PRIMARY_BLUE

    p_l1 = tf_l.add_paragraph()
    p_l1.space_after = Pt(12)
    r_l1 = p_l1.add_run()
    r_l1.text = "Loss to Follow-up After Abnormal Screening:\n"
    r_l1.font.bold = True
    r_l1.font.size = Pt(14)
    r_l1.font.color.rgb = COLOR_NAVY_DARK

    p_l2 = tf_l.add_paragraph()
    p_l2.space_after = Pt(12)
    add_text_with_fill_highlight(
        p_l2,
        "[FILL: 2-3 verified citations on loss to follow-up after abnormal screening results, with author/organization, year and link. Do NOT invent references; leave the marker if none are verified.]",
        default_color=COLOR_TEXT_MAIN,
        default_size=Pt(14)
    )

    p_l3 = tf_l.add_paragraph()
    r_l3 = p_l3.add_run()
    r_l3.text = "Core Challenge Identified: Fragmented coordination, manual telephone outreach, and lack of verified handoff tracking lead to high attrition between abnormal screening and timely diagnostic resolution."
    r_l3.font.size = Pt(13)
    r_l3.font.color.rgb = COLOR_TEXT_MUTED

    # Right Column: Prior Testing of CareBridge
    right_card = s7.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.8), col_y, col_w, col_h)
    right_card.fill.solid()
    right_card.fill.fore_color.rgb = COLOR_WHITE
    right_card.line.color.rgb = COLOR_ACCENT_TEAL
    right_card.line.width = Pt(1.5)
    tf_r = right_card.text_frame
    tf_r.word_wrap = True
    tf_r.margin_left = Inches(0.3)
    tf_r.margin_right = Inches(0.3)
    tf_r.margin_top = Inches(0.25)

    p_rt = tf_r.paragraphs[0]
    p_rt.space_after = Pt(10)
    r_rt = p_rt.add_run()
    r_rt.text = "Prior Testing of CareBridge"
    r_rt.font.bold = True
    r_rt.font.size = Pt(18)
    r_rt.font.color.rgb = COLOR_ACCENT_TEAL

    testing_bullets = [
        ("Verification Command: ", "pytest backend\\tests -q (22 test suites)"),
        ("Pass / Failure Counts: ", "215 passed, 20 failed (unmodified baseline), 3 warnings in 269s"),
        ("Phase 5 Acceptance: ", "8 passed / 0 failed in 4.78s (100% passing across domain synchronization)"),
        ("End-to-End Scenarios: ", "Scenario A (16-step complete care loop from screening intake to verified doctor closure) verified passing on synthetic data cohort."),
        ("Fault Injection Recovery: ", "Verified recovery plays for missed appointments, corrupted projections, and SSE connection interruptions.")
    ]
    for b_title, b_val in testing_bullets:
        p_b = tf_r.add_paragraph()
        p_b.space_after = Pt(8)
        r_bt = p_b.add_run()
        r_bt.text = "•  " + b_title
        r_bt.font.bold = True
        r_bt.font.size = Pt(13)
        r_bt.font.color.rgb = COLOR_NAVY_DARK
        r_bv = p_b.add_run()
        r_bv.text = b_val
        r_bv.font.size = Pt(13)
        r_bv.font.color.rgb = COLOR_TEXT_MAIN

    # Bottom Note: "All testing used synthetic data."
    note_box = s7.shapes.add_textbox(Inches(0.65), Inches(6.35), Inches(12.0), Inches(0.5))
    tf_n = note_box.text_frame
    p_n = tf_n.paragraphs[0]
    p_n.alignment = PP_ALIGN.CENTER
    r_n = p_n.add_run()
    r_n.text = "Note: All testing used synthetic data."
    r_n.font.bold = True
    r_n.font.size = Pt(13)
    r_n.font.color.rgb = COLOR_PRIMARY_BLUE

    # =========================================================================
    # SLIDE 8: DATA SOURCES AND LEGAL RIGHT TO USE THEM
    # =========================================================================
    print("Building Slide 8: Data Sources & Legal Right to Use Them...")
    s8 = add_slide_with_bg(8)

    headers_s8 = ["Source", "Type", "Owner", "Sensitivity", "Permission", "Personal data?"]
    rows_s8 = [
        ["Synthetic patient records, reports, appointments", "Generated test data", "Ai_Mavericks", "Low (fictional)", "Own creation", "No"],
        ["FHIR R4 resource schemas / specifications", "Public standard", "HL7", "None", "Public specification", "No"],
        ["Clinical education content / pathways", "Authored by team", "Ai_Mavericks", "Low", "Own creation;\n[FILL: reviewer]", "No"],
        ["LLM inference (Groq-hosted model)", "Third-party API", "Groq / provider", "Prompts have NO PHI", "Provider terms of service", "No (synthetic only)"]
    ]
    col_widths_s8 = [Inches(3.2), Inches(1.8), Inches(1.5), Inches(1.9), Inches(2.2), Inches(1.4)]
    create_table(s8, Inches(0.65), Inches(2.1), Inches(12.0), Inches(3.6), headers_s8, rows_s8, col_widths_s8, font_size=Pt(13))

    # Footer note
    ft_box = s8.shapes.add_textbox(Inches(0.65), Inches(6.0), Inches(12.0), Inches(0.6))
    tf_ft = ft_box.text_frame
    tf_ft.word_wrap = True
    p_ft = tf_ft.paragraphs[0]
    p_ft.alignment = PP_ALIGN.CENTER
    r_ft = p_ft.add_run()
    r_ft.text = "“No real patient data is used. Any real deployment would need consent, data-processing agreements and local regulatory review.”"
    r_ft.font.bold = True
    r_ft.font.size = Pt(14)
    r_ft.font.color.rgb = COLOR_PRIMARY_BLUE

    # =========================================================================
    # SLIDE 9: RISKS AND SAFEGUARDS
    # =========================================================================
    print("Building Slide 9: Risks and Safeguards...")
    s9 = add_slide_with_bg(9)

    headers_s9 = ["Risk", "Safeguard"]
    rows_s9 = [
        ["Privacy", "Synthetic data only; role- and case-scoped access; no secrets or clinical detail in logs"],
        ["Security", "JWT auth, role checks enforced in code (not prompts), cross-patient access tests"],
        ["AI fabrication", "Replies may claim an action only if a matching successful tool result exists; failures shown honestly"],
        ["Bias / language", "English, Arabic (RTL) and Spanish; tolerant of misspellings; clarification on ambiguous high-impact info"],
        ["Explainability", "Reports explained with documented findings separated from AI interpretation; evidence shown per lifecycle stage"],
        ["Misuse", "AI never diagnoses or prescribes; clinical decisions and closure only by authorized doctors"],
        ["Human oversight", "Doctor sign-off for review, confirmation and closure; coordinator escalation on timeouts"],
        ["Failure modes", "Transactional outbox with retries; urgent escalation uses deterministic rules if the LLM is down; reconciliation tasks for conflicting evidence"]
    ]
    col_widths_s9 = [Inches(2.4), Inches(9.6)]
    create_table(s9, Inches(0.65), Inches(1.85), Inches(12.0), Inches(4.5), headers_s9, rows_s9, col_widths_s9, font_size=Pt(12.5))

    # =========================================================================
    # SLIDE 10: HARDWARE REQUIREMENTS
    # =========================================================================
    print("Building Slide 10: Hardware Requirements...")
    s10 = add_slide_with_bg(10)

    card10 = s10.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.5), Inches(2.2), Inches(10.33), Inches(3.8))
    card10.fill.solid()
    card10.fill.fore_color.rgb = COLOR_WHITE
    card10.line.color.rgb = COLOR_ACCENT_TEAL
    card10.line.width = Pt(2.0)
    tf10 = card10.text_frame
    tf10.word_wrap = True
    tf10.margin_left = Inches(0.5)
    tf10.margin_right = Inches(0.5)
    tf10.margin_top = Inches(0.5)

    p10_1 = tf10.paragraphs[0]
    p10_1.space_after = Pt(18)
    r10_1 = p10_1.add_run()
    r10_1.text = "None. CareBridge is a software-only web application.\nNo wearables, sensors or connected devices."
    r10_1.font.bold = True
    r10_1.font.size = Pt(22)
    r10_1.font.color.rgb = COLOR_PRIMARY_BLUE

    bullets10 = [
        ("Deployment Model: ", "Cloud-native or on-premise containerized deployment (Docker / Kubernetes)."),
        ("End-User Access: ", "Runs seamlessly on any modern web browser (desktop, tablet, or smartphone)."),
        ("Infrastructure: ", "FastAPI application runtime, PostgreSQL 17 relational database, Node.js frontend."),
        ("Medical Devices: ", "Zero dependence on proprietary hospital hardware, wearable monitors, or biometric sensors.")
    ]
    for b_title, b_val in bullets10:
        p10_b = tf10.add_paragraph()
        p10_b.space_after = Pt(10)
        r_bt = p10_b.add_run()
        r_bt.text = "•  " + b_title
        r_bt.font.bold = True
        r_bt.font.size = Pt(15)
        r_bt.font.color.rgb = COLOR_NAVY_DARK
        r_bv = p10_b.add_run()
        r_bv.text = b_val
        r_bv.font.size = Pt(15)
        r_bv.font.color.rgb = COLOR_TEXT_MAIN

    # =========================================================================
    # SLIDE 11: ACCESS CREDENTIALS
    # =========================================================================
    print("Building Slide 11: Access Credentials...")
    s11 = add_slide_with_bg(11)

    headers_s11 = ["Role", "Username", "Password", "What to try"]
    rows_s11 = [
        ["PATIENT", "[FILL]", "[FILL]", "Intake chat, 14-stage timeline, multilingual report explanation"],
        ["DOCTOR", "[FILL]", "[FILL]", "Assigned cases queue, diagnostic review, consultation notes, closure sign-off"],
        ["CARE_COORDINATOR", "[FILL]", "[FILL]", "New screening requirements queue, orders, doctor allocation, SLA monitoring"]
    ]
    col_widths_s11 = [Inches(2.5), Inches(1.8), Inches(1.8), Inches(5.9)]
    create_table(s11, Inches(0.65), Inches(2.2), Inches(12.0), Inches(2.6), headers_s11, rows_s11, col_widths_s11, font_size=Pt(14))

    # Demo URL and note
    demo_box = s11.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.65), Inches(5.2), Inches(12.0), Inches(1.2))
    demo_box.fill.solid()
    demo_box.fill.fore_color.rgb = COLOR_BOX_BG
    demo_box.line.color.rgb = COLOR_BORDER
    demo_box.line.width = Pt(1.5)
    tf_d = demo_box.text_frame
    tf_d.word_wrap = True
    tf_d.margin_left = Inches(0.3)
    tf_d.margin_right = Inches(0.3)
    tf_d.margin_top = Inches(0.18)

    p_d1 = tf_d.paragraphs[0]
    p_d1.space_after = Pt(6)
    add_text_with_fill_highlight(p_d1, "Demo URL: [FILL]. Synthetic accounts only. Credentials valid until [FILL: date].", default_color=COLOR_PRIMARY_BLUE, default_size=Pt(15), is_bold=True)

    p_d2 = tf_d.add_paragraph()
    r_d2 = p_d2.add_run()
    r_d2.text = "Security Notice: Dedicated synthetic demonstration accounts only; real clinical credentials are never used."
    r_d2.font.italic = True
    r_d2.font.size = Pt(13)
    r_d2.font.color.rgb = COLOR_TEXT_MUTED

    # =========================================================================
    # SLIDE 12: PATH TO PILOT AND SCALE
    # =========================================================================
    print("Building Slide 12: Path to Pilot and Scale...")
    s12 = add_slide_with_bg(12)

    col12_w = Inches(3.85)
    col12_h = Inches(2.6)
    col12_y = Inches(1.85)
    timeline_stages = [
        ("Now (Prototype)", COLOR_PRIMARY_BLUE, [
            "End-to-end workflow on synthetic data cohort.",
            "Hardening of 14-stage lifecycle, transactional outbox, and audit traceability.",
            "Verified test suite across all 3 roles with zero regressions."
        ]),
        ("Pilot (Assumption: [FILL: months])", COLOR_ACCENT_AMBER, [
            "Deploy in 1 hospital or regional screening programme.",
            "Single care pathway (e.g. breast screening to biopsy).",
            "Active evaluation of 3 roles; clinical safety review.",
            "Measured strictly against Slide 6 KPI metrics."
        ]),
        ("Scale (Expansion)", COLOR_ACCENT_TEAL, [
            "Hospital EHR/HIE integration via FHIR R4 standard.",
            "For Abu Dhabi, assess Malaffi connectivity.",
            "Expand to multi-condition oncology & chronic screening.",
            "Cross-facility regional care-coordination network."
        ])
    ]
    for idx, (t_title, t_color, t_bullets) in enumerate(timeline_stages):
        tx = Inches(0.65) + idx * (col12_w + Inches(0.22))
        tcard = s12.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, tx, col12_y, col12_w, col12_h)
        tcard.fill.solid()
        tcard.fill.fore_color.rgb = COLOR_WHITE
        tcard.line.color.rgb = t_color
        tcard.line.width = Pt(1.5)
        tf = tcard.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.2)
        tf.margin_right = Inches(0.2)
        tf.margin_top = Inches(0.18)

        p_tt = tf.paragraphs[0]
        p_tt.space_after = Pt(8)
        add_text_with_fill_highlight(p_tt, t_title, default_color=t_color, default_size=Pt(15), is_bold=True)

        for tb in t_bullets:
            p_tb = tf.add_paragraph()
            p_tb.space_after = Pt(4)
            r_dot = p_tb.add_run()
            r_dot.text = "• "
            r_dot.font.bold = True
            r_dot.font.size = Pt(12.5)
            r_dot.font.color.rgb = t_color
            r_txt = p_tb.add_run()
            r_txt.text = tb
            r_txt.font.size = Pt(12.5)
            r_txt.font.color.rgb = COLOR_TEXT_MAIN

    # Bottom Sections: Stakeholders, Regulatory, Sustainability
    bot_y = Inches(4.6)
    bot_w = Inches(12.0)
    bot_box = s12.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.65), bot_y, bot_w, Inches(2.1))
    bot_box.fill.solid()
    bot_box.fill.fore_color.rgb = COLOR_BOX_BG
    bot_box.line.color.rgb = COLOR_BORDER
    bot_box.line.width = Pt(1.5)
    tf_b = bot_box.text_frame
    tf_b.word_wrap = True
    tf_b.margin_left = Inches(0.25)
    tf_b.margin_right = Inches(0.25)
    tf_b.margin_top = Inches(0.15)

    bot_sections = [
        ("Stakeholders: ", "Hospital operations, screening programme leads, attending clinicians, IT/security officers, and patients."),
        ("Regulatory: ", "Independent privacy/security assessment and local health-authority requirements before real patient data; no compliance claimed today."),
        ("Sustainability: ", "Per-facility SaaS or tiered licensing [FILL: model], with clear cost drivers (LLM inference, cloud hosting, clinical support).")
    ]
    for idx, (sec_title, sec_desc) in enumerate(bot_sections):
        p_sec = tf_b.paragraphs[0] if idx == 0 else tf_b.add_paragraph()
        p_sec.space_after = Pt(6)
        r_st = p_sec.add_run()
        r_st.text = sec_title
        r_st.font.bold = True
        r_st.font.size = Pt(13)
        r_st.font.color.rgb = COLOR_PRIMARY_BLUE
        add_text_with_fill_highlight(p_sec, sec_desc, default_color=COLOR_TEXT_MAIN, default_size=Pt(13))

    # =========================================================================
    # SLIDE 13: PRE-EXISTING IP AND THIRD-PARTY MATERIALS
    # =========================================================================
    print("Building Slide 13: Pre-existing IP & Third-Party Materials...")
    s13 = add_slide_with_bg(13)

    headers_s13 = ["Component", "License", "Ownership / Restriction"]
    rows_s13 = [
        ["FastAPI, SQLAlchemy, Next.js, React, LangGraph", "MIT License (verified in package manifests)", "Third-party open-source, used as project dependencies"],
        ["PostgreSQL 17 Database Engine", "PostgreSQL License", "Third-party open-source relational database"],
        ["FHIR R4 Resource Standards", "HL7 Public Specification", "Third-party healthcare interoperability standard"],
        ["Groq-Hosted LLM API", "Commercial Terms of Service", "Third-party inference service; no real PHI transmitted"],
        ["CareBridge Application Code & Workflows", "Proprietary / [FILL]", "Ai_Mavericks: Agent prompts, lifecycle logic & domain services"]
    ]
    col_widths_s13 = [Inches(4.2), Inches(3.4), Inches(4.4)]
    create_table(s13, Inches(0.65), Inches(2.1), Inches(12.0), Inches(3.8), headers_s13, rows_s13, col_widths_s13, font_size=Pt(13))

    # =========================================================================
    # SLIDE 14: CONFLICT OF INTEREST DECLARATION
    # =========================================================================
    print("Building Slide 14: Conflict of Interest Declaration...")
    s14 = add_slide_with_bg(14)

    card14 = s14.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.5), Inches(2.3), Inches(10.33), Inches(3.2))
    card14.fill.solid()
    card14.fill.fore_color.rgb = COLOR_WHITE
    card14.line.color.rgb = COLOR_BORDER
    card14.line.width = Pt(1.5)
    tf14 = card14.text_frame
    tf14.word_wrap = True
    tf14.margin_left = Inches(0.5)
    tf14.margin_right = Inches(0.5)
    tf14.margin_top = Inches(0.4)

    p14_t = tf14.paragraphs[0]
    p14_t.space_after = Pt(16)
    r14_t = p14_t.add_run()
    r14_t.text = "Team Conflict of Interest Declaration"
    r14_t.font.bold = True
    r14_t.font.size = Pt(20)
    r14_t.font.color.rgb = COLOR_PRIMARY_BLUE

    p14_body = tf14.add_paragraph()
    p14_body.space_after = Pt(14)
    add_text_with_fill_highlight(
        p14_body,
        "[FILL: confirm. If true: 'The team has no relationships with the organizers, partners (Microsoft, Inception, MBZUAI) or judges to disclose.']",
        default_color=COLOR_TEXT_MAIN,
        default_size=Pt(16)
    )

    p14_foot = tf14.add_paragraph()
    r14_f = p14_foot.add_run()
    r14_f.text = "Submitted by team Ai_Mavericks for the Future Health Digital Innovation Challenge."
    r14_f.font.italic = True
    r14_f.font.size = Pt(13)
    r14_f.font.color.rgb = COLOR_TEXT_MUTED

    # =========================================================================
    # SLIDE 15: ADDITIONAL SLIDE (CareBridge in one view)
    # =========================================================================
    print("Building Slide 15: CareBridge in One View...")
    s15 = add_slide_with_bg(15)

    # Clean mask to cover the bottom-left template text "Additional Slide"
    mask_s15 = s15.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.4), Inches(5.9), Inches(3.5), Inches(1.2))
    mask_s15.fill.solid()
    mask_s15.fill.fore_color.rgb = COLOR_WHITE
    mask_s15.line.fill.solid()
    mask_s15.line.fill.fore_color.rgb = COLOR_WHITE

    # Title box at top
    t_box15 = s15.shapes.add_textbox(Inches(0.65), Inches(1.15), Inches(12.0), Inches(0.6))
    tf_t15 = t_box15.text_frame
    p_t15 = tf_t15.paragraphs[0]
    r_t15 = p_t15.add_run()
    r_t15.text = "CareBridge in One View"
    r_t15.font.bold = True
    r_t15.font.size = Pt(22)
    r_t15.font.name = 'Arial'
    r_t15.font.color.rgb = COLOR_NAVY_DARK

    # 4 Structured Visual Cards (2x2 grid)
    grid_w = Inches(5.85)
    grid_h = Inches(1.95)
    gx1 = Inches(0.65)
    gx2 = Inches(6.8)
    gy1 = Inches(1.85)
    gy2 = Inches(4.0)

    cards_15 = [
        (gx1, gy1, "Problem", COLOR_RED_FILL,
         "Patients are lost between screening, result, specialist and follow-up due to disconnected systems, manual phone outreach, and unverified handoffs."),
        (gx2, gy1, "Solution", COLOR_PRIMARY_BLUE,
         "Role-aware AI agents on one unified, evidence-driven care coordination workflow connecting Patients, Care Coordinators, and Attending Doctors."),
        (gx1, gy2, "Differentiator", COLOR_ACCENT_TEAL,
         "Stages complete ONLY from persisted clinical evidence; AI cannot claim what the database cannot prove; transactional outbox guarantees durable notifications."),
        (gx2, gy2, "Ask / Next Step", COLOR_ACCENT_AMBER,
         "[FILL: pilot partner or support requested]")
    ]

    for cx, cy, title, color, text in cards_15:
        card = s15.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, cy, grid_w, grid_h)
        card.fill.solid()
        card.fill.fore_color.rgb = COLOR_WHITE
        card.line.color.rgb = color
        card.line.width = Pt(1.5)
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.25)
        tf.margin_right = Inches(0.25)
        tf.margin_top = Inches(0.18)

        p_t = tf.paragraphs[0]
        p_t.space_after = Pt(6)
        r_t = p_t.add_run()
        r_t.text = title
        r_t.font.bold = True
        r_t.font.size = Pt(16)
        r_t.font.color.rgb = color

        p_b = tf.add_paragraph()
        add_text_with_fill_highlight(p_b, text, default_color=COLOR_TEXT_MAIN, default_size=Pt(14))

    # Bottom caption
    foot15 = s15.shapes.add_textbox(Inches(0.65), Inches(6.25), Inches(12.0), Inches(0.5))
    tf_f15 = foot15.text_frame
    p_f15 = tf_f15.paragraphs[0]
    p_f15.alignment = PP_ALIGN.CENTER
    r_f15 = p_f15.add_run()
    r_f15.text = "CareBridge: Software-only, role-isolated care coordination built for measurable clinical loop closure."
    r_f15.font.italic = True
    r_f15.font.size = Pt(13)
    r_f15.font.color.rgb = COLOR_PRIMARY_BLUE

    # =========================================================================
    # SLIDE 16: THANK YOU SLIDE (Leave unchanged)
    # =========================================================================
    print("Building Slide 16: Thank You...")
    s16 = add_slide_with_bg(16)
    # Kept completely unchanged as requested.

    # Save presentation
    output_pptx = "AiMavericks_CareBridge_Submission.pptx"
    prs.save(output_pptx)
    print(f"Presentation successfully saved to: {output_pptx}")
    return output_pptx


if __name__ == "__main__":
    pdf_template = r"C:\Users\HARIHARAN\.gemini\antigravity\brain\6fe99c1c-988c-4056-a3aa-8ca616551c7e\.user_uploaded\media_1795125833848_9983f5d2.pdf"
    bg_dir = r"C:\CareBridge\template_bgs"
    bg_images = render_template_backgrounds(pdf_template, bg_dir)
    build_presentation(bg_images)
