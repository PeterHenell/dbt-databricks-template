select
    customer_id,
    count(*) as number_of_orders,
    sum(total_price) as lifetime_value,
    min(order_date) as first_order_date,
    max(order_date) as most_recent_order_date
from {{ ref('stg_tpch__orders') }}
group by customer_id
