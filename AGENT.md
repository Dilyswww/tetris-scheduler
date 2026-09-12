# Tetris (HackCMU 2026)

## Description

The application is a calendar dynamic adjustment app. The general goal is to
help people maintain a realistic daily plan when unexpected changes occur,
reducing the effort and stress of manually rearranging their schedules.

The user actions are:

0. There are three type of tasks: fixed event, flexible task, and pinned task
1. Add flexible tasks to be completed before a deadline
2. Add fixed event that have a fixed begin and end time
3. Pin a task or event
4. Running late or extend the current work slot

The assumptions to make are:

1. Have a fixed time unbreakable slot: every 30 minutes
2. Have a fixed start time and end time every day (8am to 12am)

The soft requirements are:

1. Make fewer moves when rescheduling, allow users to easily see the changes and
   option to undo (choose a smart algorithm)
2. (To be extended)

## Implementation

The folder structure looks like this:

- `doc` for any details for architecture, algorithms as markdown files
- `backend` for the python backend and optimizer using fastapi
- `frontend` for a react webpage for user interaction

Implementation Order:

Phase 1

- Static calendar UI
- Task struct types
- Placeholder dumb optimizer algo for placing flexible tasks
- Allow adding and removing fixed events and flexible tasks
- Pin task

Phase 2

- Optimizer Algorithm
- Extend task / running late
- Infeasibility / defer task
- Movement penalty

Phase 3

- Integration with Google Calendar

## Sponsor

We should ideally use some sponsor's tool (if relevant and possible)

- Gemini API
- ElevenLabs
- Solana
- Vultr
- Auth0
- MongoDB Atlas
