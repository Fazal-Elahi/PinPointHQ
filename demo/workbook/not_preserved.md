# What this migration cannot carry

- time-of-day and timezone on original application dates (date_value is format:date)
- original created_at on all records (read-only on both surfaces)
- job association for Tier 2 rows beyond a tag
