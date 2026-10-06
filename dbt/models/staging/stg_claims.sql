-- One row per claim across inpatient, outpatient, carrier and Part D, with allowed cost rebuilt
-- from the payment fields (same definitions as the Kedro ingest) and the simulated paid date.
WITH unioned AS (
    SELECT DESYNPUF_ID AS member_id, CLM_ID AS claim_id, 'IP' AS source,
           MIN({{ try_yyyymmdd('CLM_FROM_DT') }}) AS from_dt,
           MAX({{ try_yyyymmdd('CLM_THRU_DT') }}) AS thru_dt,
           SUM({{ num('CLM_PMT_AMT') }} + {{ num('NCH_PRMRY_PYR_CLM_PD_AMT') }}
               + {{ num('NCH_BENE_IP_DDCTBL_AMT') }} + {{ num('NCH_BENE_PTA_COINSRNC_LBLTY_AM') }}
               + {{ num('NCH_BENE_BLOOD_DDCTBL_LBLTY_AM') }}) AS allowed,
           SUM({{ num('CLM_UTLZTN_DAY_CNT') }}) AS ip_days,
           CAST(NULL AS VARCHAR) AS ndc
    FROM {{ source('raw', 'inpatient') }}
    GROUP BY 1, 2

    UNION ALL
    SELECT DESYNPUF_ID, CLM_ID, 'OP',
           MIN({{ try_yyyymmdd('CLM_FROM_DT') }}), MAX({{ try_yyyymmdd('CLM_THRU_DT') }}),
           SUM({{ num('CLM_PMT_AMT') }} + {{ num('NCH_PRMRY_PYR_CLM_PD_AMT') }}
               + {{ num('NCH_BENE_PTB_DDCTBL_AMT') }} + {{ num('NCH_BENE_PTB_COINSRNC_AMT') }}
               + {{ num('NCH_BENE_BLOOD_DDCTBL_LBLTY_AM') }}),
           0, NULL
    FROM {{ source('raw', 'outpatient') }}
    GROUP BY 1, 2

    UNION ALL
    SELECT DESYNPUF_ID, CLM_ID, 'CAR',
           MIN({{ try_yyyymmdd('CLM_FROM_DT') }}), MAX({{ try_yyyymmdd('CLM_THRU_DT') }}),
           SUM({{ carrier_allowed() }}), 0, NULL
    FROM {{ source('raw', 'carrier') }}
    GROUP BY 1, 2

    UNION ALL
    SELECT DESYNPUF_ID, PDE_ID, 'RX',
           {{ try_yyyymmdd('SRVC_DT') }}, {{ try_yyyymmdd('SRVC_DT') }},
           {{ num('TOT_RX_CST_AMT') }}, 0, PROD_SRVC_ID
    FROM {{ source('raw', 'pde') }}
)
SELECT u.member_id, u.claim_id, u.source, u.from_dt, u.thru_dt,
       GREATEST(u.allowed, 0) AS allowed, u.ip_days, u.ndc,
       CAST(p.paid_dt AS DATE) AS paid_dt
FROM unioned u
LEFT JOIN {{ source('kedro', 'claims') }} p
  ON p.source = u.source AND p.claim_id = u.claim_id AND p.member_id = u.member_id
WHERE u.from_dt IS NOT NULL
