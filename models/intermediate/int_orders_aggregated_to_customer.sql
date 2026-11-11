select
    orders.customer_id,
    count(*) as number_of_orders,
    count_if(order_statuses.is_open) as number_of_open_orders,
    sum(orders.total_price) as lifetime_value,
    min(orders.order_date) as first_order_date,
    max(orders.order_date) as most_recent_order_date
from {{ ref('stg_tpch__orders') }} as orders
left join {{ ref('order_statuses') }} as order_statuses
    on orders.order_status = order_statuses.order_status
group by orders.customer_id
