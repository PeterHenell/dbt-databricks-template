-- Sample data: a plain select that generates a few rows, so the template builds
-- without any source. A staging model on a real source reads it with source()
-- instead (docs/first-models.md, step 6).
select
    cast(customer_id as bigint) as customer_id,
    customer_name,
    market_segment,
    cast(nation_id as bigint) as nation_id
from
    values
    (1, 'Ada', 'BUILDING', 7),
    (2, 'Grace', 'MACHINERY', 21),
    (3, 'Linus', 'AUTOMOBILE', 7),
    (4, 'Margaret', 'HOUSEHOLD', 3) -- has no orders, on purpose
        as customers (customer_id, customer_name, market_segment, nation_id)
