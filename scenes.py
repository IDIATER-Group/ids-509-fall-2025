# 5 progressive mystery scenes with detailed context and hints
def get_scenes():
    return [
        {
            'id': 1,
            'title': 'Inventory Anomaly',
            'story': '''
Our first case involves basic inventory analysis. The New York warehouse reported receiving 500 Widgets, 
but their system shows a different number in stock. We need to verify the current Widget inventory in New York.

Hint: Join the inventory table with products and warehouses to find the specific stock level.
''',
            'question': 'How many Widgets are currently in stock at the New York warehouse?',
            'answer_sql': '''
SELECT i.stock
FROM inventory i
JOIN products p ON i.product_id = p.product_id
JOIN warehouses w ON i.warehouse_id = w.warehouse_id
WHERE p.name = 'Widget' AND w.location = 'New York';
'''
        },
        {
            'id': 2,
            'title': 'Supplier Reliability Check',
            'story': '''
We've noticed some inconsistencies with Globex's deliveries to Berlin. We need to analyze their reliability score
and recent shipment history. This could explain some of our inventory discrepancies.

Hint: The suppliers table contains reliability scores, and you'll need to join with shipments to see their history.
''',
            'question': 'What is Globex\'s reliability score and how many shipments have they made to Berlin?',
            'answer_sql': '''
SELECT s.reliability_score, COALESCE(COUNT(sh.shipment_id), 0) as total_shipments
FROM suppliers s
LEFT JOIN shipments sh ON s.supplier_id = sh.supplier_id
LEFT JOIN warehouses w ON sh.warehouse_id = w.warehouse_id AND w.location = 'Berlin'
WHERE s.name = 'Globex'
GROUP BY s.supplier_id, s.reliability_score;
'''
        },
        {
            'id': 3,
            'title': 'Warehouse Capacity Crisis',
            'story': '''
The Tokyo warehouse is reporting storage issues. We need to analyze their current capacity utilization
by comparing their total inventory against their maximum capacity.

Hint: You'll need to sum up all inventory quantities and compare with the warehouse capacity.
''',
            'question': 'What percentage of Tokyo\'s warehouse capacity is currently utilized?',
            'answer_sql': '''
SELECT ROUND(CAST(SUM(i.stock) AS FLOAT) / w.capacity * 100, 2) as utilization_percentage
FROM inventory i
JOIN warehouses w ON i.warehouse_id = w.warehouse_id
WHERE w.location = 'Tokyo'
GROUP BY w.warehouse_id, w.capacity;
'''
        },
        {
            'id': 4,
            'title': 'Suspicious Shipment Patterns',
            'story': '''
We've detected unusual patterns in recent shipments. Some products are showing up in inventory
before their recorded delivery dates. Focus on shipments to Berlin in the last week.

Hint: Compare shipment_date with received_date and look for inconsistencies.
''',
            'question': 'Find shipments where the received_date is earlier than the shipment_date:',
            'answer_sql': '''
SELECT p.name, s.name as supplier, sh.shipment_date, sh.received_date
FROM shipments sh
JOIN products p ON sh.product_id = p.product_id
JOIN suppliers s ON sh.supplier_id = s.supplier_id
JOIN warehouses w ON sh.warehouse_id = w.warehouse_id
WHERE w.location = 'Berlin'
AND sh.received_date < sh.shipment_date;
'''
        },
        {
            'id': 5,
            'title': 'The Final Connection',
            'story': '''
It's time to connect all the evidence. We're looking for products that meet ALL these criteria:
1. Have more inventory than total shipments received
2. Came from suppliers with low reliability scores (<90)
3. Are stored in warehouses near capacity (>90%)

Hint: You'll need to use subqueries or CTEs to combine all these conditions.
''',
            'question': 'Find suspicious products meeting all criteria:',
            'answer_sql': '''
WITH inventory_vs_shipments AS (
    SELECT 
        p.product_id,
        p.name as product_name,
        SUM(i.stock) as total_inventory,
        SUM(sh.quantity) as total_shipped
    FROM products p
    JOIN inventory i ON p.product_id = i.product_id
    LEFT JOIN shipments sh ON p.product_id = sh.product_id
    GROUP BY p.product_id, p.name
    HAVING SUM(i.stock) > COALESCE(SUM(sh.quantity), 0)
),
low_reliability_suppliers AS (
    SELECT DISTINCT product_id
    FROM shipments sh
    JOIN suppliers s ON sh.supplier_id = s.supplier_id
    WHERE s.reliability_score < 90
),
high_capacity_warehouses AS (
    SELECT DISTINCT i.product_id
    FROM inventory i
    JOIN warehouses w ON i.warehouse_id = w.warehouse_id
    WHERE i.stock > w.capacity * 0.9
)
SELECT 
    ivs.product_name,
    ivs.total_inventory,
    COALESCE(ivs.total_shipped, 0) as total_shipped,
    ivs.total_inventory - ivs.total_shipped as excess_inventory
FROM inventory_vs_shipments ivs
JOIN low_reliability_suppliers lrs ON ivs.product_id = lrs.product_id
JOIN high_capacity_warehouses hcw ON ivs.product_id = hcw.product_id;
'''
        }
    ]
