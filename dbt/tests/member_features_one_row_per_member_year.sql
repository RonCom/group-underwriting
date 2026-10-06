SELECT member_id, feature_year, COUNT(*) AS n
FROM {{ ref('member_features') }}
GROUP BY 1, 2
HAVING COUNT(*) > 1
