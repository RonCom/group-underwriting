-- Point-in-time claim features and next-year target for each (member, feature year) the Kedro
-- cohort step selected. Mirrors group_underwriting.pipelines.features.nodes.build_features.
WITH rows AS (
    SELECT member_id, feature_year,
           CAST(CAST(feature_year AS VARCHAR) || '-12-31' AS DATE) AS cutoff
    FROM {{ source('kedro', 'member_groups') }}
),
past AS (
    SELECT r.member_id, r.feature_year, c.*
    FROM rows r
    JOIN {{ ref('stg_claims') }} c
      ON c.member_id = r.member_id
     AND EXTRACT(year FROM c.from_dt) = r.feature_year
     AND c.paid_dt <= {{ add_months('r.cutoff', var('runout_months')) }}
),
claim_features AS (
    SELECT member_id, feature_year,
           SUM(CASE WHEN source = 'IP' THEN allowed ELSE 0 END) AS cost_ip,
           SUM(CASE WHEN source = 'OP' THEN allowed ELSE 0 END) AS cost_op,
           SUM(CASE WHEN source = 'CAR' THEN allowed ELSE 0 END) AS cost_car,
           SUM(CASE WHEN source = 'RX' THEN allowed ELSE 0 END) AS cost_rx,
           SUM(allowed) AS cost_total,
           SUM(CASE WHEN EXTRACT(month FROM from_dt) >= 7 THEN allowed ELSE 0 END) AS cost_h2,
           MAX(allowed) AS max_claim,
           SUM(CASE WHEN source = 'IP' THEN 1 ELSE 0 END) AS n_ip_stays,
           SUM(ip_days) AS ip_days,
           SUM(CASE WHEN source = 'OP' THEN 1 ELSE 0 END) AS n_op,
           SUM(CASE WHEN source = 'CAR' THEN 1 ELSE 0 END) AS n_car,
           SUM(CASE WHEN source = 'RX' THEN 1 ELSE 0 END) AS n_rx,
           COUNT(DISTINCT CASE WHEN source = 'RX' THEN ndc END) AS n_ndc,
           SUM(CASE WHEN source = 'RX' AND allowed > {{ var('specialty_rx_threshold') }}
                    THEN 1 ELSE 0 END) AS n_specialty_rx,
           COUNT(DISTINCT EXTRACT(month FROM from_dt)) AS months_with_claims
    FROM past
    GROUP BY 1, 2
),
target AS (
    SELECT r.member_id, r.feature_year, SUM(c.allowed) AS target_cost
    FROM rows r
    JOIN {{ ref('stg_claims') }} c
      ON c.member_id = r.member_id AND EXTRACT(year FROM c.from_dt) = r.feature_year + 1
    GROUP BY 1, 2
)
SELECT
    r.member_id,
    r.feature_year,
    {{ days_between('m.birth_dt', 'r.cutoff') }} / 365.25 AS age,
    CASE WHEN m.sex = 2 THEN 1 ELSE 0 END AS female,
    CASE WHEN m.esrd THEN 1 ELSE 0 END AS esrd,
    LEAST(GREATEST(LEAST(m.months_a, m.months_b), 0), 12) AS months_ab,
    LEAST(GREATEST(COALESCE(m.months_d, 0), 0), 12) AS months_d,
    {% for c in ['alzheimers', 'chf', 'ckd', 'cancer', 'copd', 'depression', 'diabetes',
                 'ischemic_heart', 'osteoporosis', 'ra_oa', 'stroke'] -%}
    CASE WHEN m.{{ c }} THEN 1 ELSE 0 END AS {{ c }},
    {% endfor -%}
    (CASE WHEN m.alzheimers THEN 1 ELSE 0 END + CASE WHEN m.chf THEN 1 ELSE 0 END
     + CASE WHEN m.ckd THEN 1 ELSE 0 END + CASE WHEN m.cancer THEN 1 ELSE 0 END
     + CASE WHEN m.copd THEN 1 ELSE 0 END + CASE WHEN m.depression THEN 1 ELSE 0 END
     + CASE WHEN m.diabetes THEN 1 ELSE 0 END + CASE WHEN m.ischemic_heart THEN 1 ELSE 0 END
     + CASE WHEN m.osteoporosis THEN 1 ELSE 0 END + CASE WHEN m.ra_oa THEN 1 ELSE 0 END
     + CASE WHEN m.stroke THEN 1 ELSE 0 END) AS n_chronic,
    {% for c in ['cost_ip', 'cost_op', 'cost_car', 'cost_rx', 'cost_total', 'cost_h2',
                 'max_claim', 'n_ip_stays', 'ip_days', 'n_op', 'n_car', 'n_rx', 'n_ndc',
                 'n_specialty_rx', 'months_with_claims'] -%}
    COALESCE(f.{{ c }}, 0) AS {{ c }},
    {% endfor -%}
    COALESCE(t.target_cost, 0) AS target_cost
FROM rows r
JOIN {{ ref('stg_members') }} m ON m.member_id = r.member_id AND m.year = r.feature_year
LEFT JOIN claim_features f ON f.member_id = r.member_id AND f.feature_year = r.feature_year
LEFT JOIN target t ON t.member_id = r.member_id AND t.feature_year = r.feature_year
