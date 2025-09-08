import io
from datetime import datetime, timedelta
from typing import Optional
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from flask import make_response, Response

from app.llm import TrainingPlan


def generate_pdf_calendar(
    training_plan: TrainingPlan, start_date: Optional[datetime] = None
) -> bytes:
    """
    Generate a PDF calendar view of the training plan.

    Args:
        training_plan: The training plan object
        start_date: Starting date for the calendar (defaults to today)

    Returns:
        PDF bytes
    """
    if start_date is None:
        start_date = datetime.now()

    # Create a buffer to store the PDF
    buffer = io.BytesIO()

    # Create the PDF document
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []

    # Get styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=30,
        alignment=1,  # Center alignment
    )

    # Add title
    title = Paragraph(f"<b>{training_plan.title}</b>", title_style)
    story.append(title)

    # Add plan details
    details_style = styles["Normal"]
    details = [
        f"<b>Duration:</b> {training_plan.duration_weeks} weeks",
        f"<b>Goal:</b> {training_plan.goal}",
        f"<b>Start Date:</b> {start_date.strftime('%B %d, %Y')}",
    ]

    for detail in details:
        story.append(Paragraph(detail, details_style))
        story.append(Spacer(1, 6))

    story.append(Spacer(1, 20))

    # Create workout lookup by week and day
    workout_lookup = {}
    for workout in training_plan.workouts:
        week_key = workout.week
        day_key = workout.day_of_week.lower()
        if week_key not in workout_lookup:
            workout_lookup[week_key] = {}
        workout_lookup[week_key][day_key] = workout

    # Generate calendar for each week
    current_date = start_date
    days_of_week = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    for week_num in range(1, training_plan.duration_weeks + 1):
        # Week header
        week_title = Paragraph(f"<b>Week {week_num}</b>", styles["Heading2"])
        story.append(week_title)
        story.append(Spacer(1, 10))

        # Create calendar table data
        calendar_data = []
        header_row = [day[:3] for day in days_of_week]  # Mon, Tue, Wed, etc.
        calendar_data.append(header_row)

        # Calculate dates for this week
        week_start = current_date
        date_row = []
        workout_row = []

        for i, day_name in enumerate(days_of_week):
            day_date = week_start + timedelta(days=i)
            date_row.append(day_date.strftime("%m/%d"))

            # Get workout for this day
            day_key = day_name.lower()
            if week_num in workout_lookup and day_key in workout_lookup[week_num]:
                workout = workout_lookup[week_num][day_key]
                workout_text = workout.workout_type
                if workout.distance_km:
                    workout_text += f"\n{workout.distance_km}km"
                if workout.duration_minutes:
                    workout_text += f"\n{workout.duration_minutes}min"
            else:
                workout_text = "Rest"

            workout_row.append(workout_text)

        calendar_data.append(date_row)
        calendar_data.append(workout_row)

        # Create table
        table = Table(calendar_data, colWidths=[1.1 * inch] * 7)

        # Style the table
        table_style = TableStyle(
            [
                # Header row styling
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                # Date row styling
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, 1), 9),
                ("BACKGROUND", (0, 1), (-1, 1), colors.lightgrey),
                # Workout row styling
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica"),
                ("FONTSIZE", (0, 2), (-1, 2), 8),
                ("BACKGROUND", (0, 2), (-1, 2), colors.beige),
                ("VALIGN", (0, 2), (-1, 2), "TOP"),
                # Grid
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("ROWBACKGROUNDS", (0, 2), (-1, 2), [colors.lightblue, colors.white]),
            ]
        )

        # Highlight workout days with darker background
        for col in range(7):
            day_name = days_of_week[col].lower()
            if week_num in workout_lookup and day_name in workout_lookup[week_num]:
                workout = workout_lookup[week_num][day_name]
                if workout.workout_type.lower() != "rest":
                    table_style.add("BACKGROUND", (col, 2), (col, 2), colors.darkblue)
                    table_style.add("TEXTCOLOR", (col, 2), (col, 2), colors.white)

        table.setStyle(table_style)
        story.append(table)
        story.append(Spacer(1, 20))

        # Move to next week
        current_date += timedelta(weeks=1)

    # Add notes if any
    if training_plan.notes:
        story.append(Spacer(1, 20))
        notes_title = Paragraph("<b>Notes:</b>", styles["Heading3"])
        story.append(notes_title)
        notes_text = Paragraph(training_plan.notes, styles["Normal"])
        story.append(notes_text)

    # Build PDF
    doc.build(story)

    # Get the PDF data
    pdf_data = buffer.getvalue()
    buffer.close()

    return pdf_data


def create_pdf_response(
    training_plan: TrainingPlan, filename: Optional[str] = None
) -> Response:
    """
    Create a Flask response with the PDF calendar.

    Args:
        training_plan: The training plan object
        filename: Name for the downloaded file

    Returns:
        Flask response object
    """
    if filename is None:
        filename = f"{training_plan.title.replace(' ', '_')}_calendar.pdf"

    pdf_data = generate_pdf_calendar(training_plan)

    response = make_response(pdf_data)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response
