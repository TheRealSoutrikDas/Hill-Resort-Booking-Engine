"""Draft reply templates, one per category (brief: drafts with placeholders).

Templates contain no numbers: prices, dates and counts arrive only through the
placeholders, which step 20 fills from the rate table in code. A placeholder that cannot
be filled stays visible for staff, never a guessed value (brief). Drafts are plain text.
"""

PLACEHOLDERS = frozenset(
    {"guest_name", "room_type", "dates", "guests", "price_total", "event_month"}
)

DRAFTS: dict[str, str] = {
    "room_booking": (
        "Dear {guest_name},\n\n"
        "Thank you for your interest in staying with us. For {guests} guests in our "
        "{room_type} on {dates}, the total comes to {price_total}, including GST.\n\n"
        "You can book directly on our website, or reply to this message and our "
        "reservations team will help you.\n\n"
        "Warm regards,\nReservations team"
    ),
    "wedding": (
        "Dear {guest_name},\n\n"
        "Thank you for thinking of us for your celebration in {event_month} for "
        "{guests} guests. Our events team will share our lawn and package details and "
        "get in touch to plan the next steps with you.\n\n"
        "Warm regards,\nEvents team"
    ),
    "corporate_offsite": (
        "Dear {guest_name},\n\n"
        "Thank you for considering us for your team's offsite in {event_month} for "
        "{guests} guests. Our events team will send a proposal covering rooms, meeting "
        "space and meals, and will be in touch shortly.\n\n"
        "Warm regards,\nEvents team"
    ),
    "complaint": (
        "Dear {guest_name},\n\n"
        "Thank you for telling us, and we are sorry your experience fell short. Our "
        "general manager has your message and will contact you personally to put "
        "things right.\n\n"
        "Sincerely,\nGeneral Manager"
    ),
    "other": (
        "Dear {guest_name},\n\n"
        "Thank you for your message. We have passed it to the right team, who will "
        "reply to you soon.\n\n"
        "Warm regards,\nThe resort team"
    ),
}
