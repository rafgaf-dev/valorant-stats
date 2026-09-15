# valorant-stats

A small React and AWS application that displays a friend's Valorant KDA, win rate,
and headshot percentage, comparing recent performance with lifetime averages.
The app reads cached statistics from its backend; a scheduled collector retrieves
fresh data from the Riot API and stores it in a relational database.

The implementation and infrastructure plan lives in [_docs/implementation-plan.md](_docs/implementation-plan.md).
