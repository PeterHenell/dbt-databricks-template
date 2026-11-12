select
    customers.customer_id,
    customers.customer_name,
    cast(coalesce(orders.number_of_orders, 0) as bigint) as number_of_orders,
    cast(coalesce(orders.number_of_open_orders, 0) as bigint) as number_of_open_orders,
    cast(coalesce(orders.lifetime_value, 0) as decimal(18, 2)) as total_order_value,
    orders.first_order_date,
    orders.most_recent_order_date
from {{ ref('stg_sample__customers') }} as customers
left join {{ ref('int_orders_aggregated_to_customer') }} as orders
    on customers.customer_id = orders.customer_id
