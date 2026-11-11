-- Sample data: a plain select that generates a few rows (see stg_sample__customers).
select
    cast(order_id as bigint) as order_id,
    cast(customer_id as bigint) as customer_id,
    order_status,
    cast(total_price as decimal(18, 2)) as total_price,
    cast(order_date as date) as order_date
from
    values
    (1, 1, 'F', 120.50, '2024-01-15'),
    (2, 1, 'O', 80.00, '2024-03-02'),
    (3, 2, 'F', 300.00, '2024-02-10'),
    (4, 2, 'P', 45.25, '2024-04-21'),
    (5, 3, 'O', 99.90, '2024-05-05')
        as orders (order_id, customer_id, order_status, total_price, order_date)
