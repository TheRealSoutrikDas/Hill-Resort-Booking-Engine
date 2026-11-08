# Enquiry classifier evaluation

Sample file: `backend/data/sample_enquiries.json`, 27 enquiries (3 from the client brief, 24 invented), received on 2026-11-05.

How to read this: category is an exact match with the expected category; lane `auto` must reach the category's lane, `unsorted` must reach Unsorted, `either` always passes; a field counts when the sample lists it. A missed required GM alert fails the run (A-139, A-140).

> The keyword rules were written from these same messages, so the keyword figures are in-sample and flatter it. A model run is the fairer test (A-144).

## Summary

| | keyword |
|---|---|
| Model | `keyword` |
| Category right | 27/27 (100%) |
| Lane right | 27/27 (100%) |
| Required GM alerts raised | 4/4 (100%) |
| False GM alerts | 0 |
| Expected fields right | 53/53 (100%) |
| Fell back to keywords | 0 |
| Median time per enquiry | n/a |
| Gate (no missed alert) | pass |

## keyword: per enquiry

| Id | Tags | Expected | Got | Category | Lane | GM alert | Fields wrong | Fields missing | Extra fields | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| ENQ-4410 | clean | wedding (auto) | wedding / wedding | yes | yes | no | - | - | - | - |
| ENQ-4411 | clean | room_booking (auto) | room_booking / room_booking | yes | yes | no | - | - | event_month, nights | - |
| ENQ-4412 | clean | corporate_offsite (auto) | corporate_offsite / corporate_offsite | yes | yes | no | - | - | - | - |
| ENQ-4413 | clean | room_booking (auto) | room_booking / room_booking | yes | yes | no | - | - | event_month, nights | - |
| ENQ-4414 | relative_date | room_booking (auto) | room_booking / room_booking | yes | yes | no | - | - | event_month | - |
| ENQ-4415 | lakh_budget, year_rollover | room_booking (auto) | room_booking / room_booking | yes | yes | no | - | - | event_month, nights | - |
| ENQ-4416 | typos, missing_guests | room_booking (auto) | room_booking / room_booking | yes | yes | no | - | - | event_month, nights | - |
| ENQ-4417 | hinglish | room_booking (either) | room_booking / room_booking | yes | yes | no | - | - | event_month, nights | - |
| ENQ-4418 | hindi | room_booking (either) | room_booking / room_booking | yes | yes | no | - | - | event_month, nights | - |
| ENQ-4419 | kannada | room_booking (either) | room_booking / room_booking | yes | yes | no | - | - | event_month, nights | - |
| ENQ-4420 | missing_guests, single_date | room_booking (auto) | room_booking / room_booking | yes | yes | no | - | - | event_month | - |
| ENQ-4421 | lakh_budget | wedding (auto) | wedding / wedding | yes | yes | no | - | - | - | - |
| ENQ-4422 | event_variant | wedding (auto) | wedding / wedding | yes | yes | no | - | - | - | - |
| ENQ-4423 | no_details | wedding (either) | wedding / unsorted | yes | yes | no | - | - | - | - |
| ENQ-4424 | over_capacity_check | wedding (auto) | wedding / wedding | yes | yes | no | - | - | - | - |
| ENQ-4425 | vague_date | corporate_offsite (auto) | corporate_offsite / corporate_offsite | yes | yes | no | - | - | - | - |
| ENQ-4426 | lakh_budget, vague_date | corporate_offsite (auto) | corporate_offsite / corporate_offsite | yes | yes | no | - | - | - | - |
| ENQ-4427 | clean | corporate_offsite (auto) | corporate_offsite / corporate_offsite | yes | yes | no | - | - | event_month | - |
| ENQ-4428 | complaint | complaint (auto) | complaint / complaint | yes | yes | yes | - | - | - | - |
| ENQ-4429 | complaint, billing | complaint (auto) | complaint / complaint | yes | yes | yes | - | - | - | - |
| ENQ-4430 | complaint_hidden, mixed_intent | complaint (auto) | complaint / complaint | yes | yes | yes | - | - | event_month, nights | - |
| ENQ-4431 | complaint, hindi | complaint (either) | complaint / complaint | yes | yes | yes | - | - | - | - |
| ENQ-4432 | mixed_intent | wedding (either) | wedding / wedding | yes | yes | no | - | - | check_in, check_out, nights | - |
| ENQ-4433 | out_of_scope | other (unsorted) | other / unsorted | yes | yes | no | - | - | - | - |
| ENQ-4434 | out_of_scope | other (unsorted) | other / unsorted | yes | yes | no | - | - | - | - |
| ENQ-4435 | too_short | other (unsorted) | other / unsorted | yes | yes | no | - | - | - | - |
| ENQ-4436 | prompt_injection | other (unsorted) | other / unsorted | yes | yes | no | - | - | - | - |
