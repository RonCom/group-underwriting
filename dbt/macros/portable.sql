{# Small cross-database helpers: the same models run on DuckDB and Snowflake. #}

{# 'YYYYMMDD' text -> DATE, NULL when blank or invalid #}
{% macro try_yyyymmdd(col) -%}
  {%- if target.type == 'snowflake' -%}
    TRY_TO_DATE(NULLIF(TRIM({{ col }}), ''), 'YYYYMMDD')
  {%- else -%}
    TRY_STRPTIME(NULLIF(TRIM({{ col }}), ''), '%Y%m%d')::DATE
  {%- endif -%}
{%- endmacro %}

{# numeric text -> DOUBLE, 0 when blank #}
{% macro num(col) -%}
  COALESCE(TRY_CAST({{ col }} AS DOUBLE), 0)
{%- endmacro %}

{# add whole months to a date #}
{% macro add_months(col, n) -%}
  {%- if target.type == 'snowflake' -%}
    DATEADD(month, {{ n }}, {{ col }})
  {%- else -%}
    ({{ col }} + INTERVAL ({{ n }}) MONTH)::DATE
  {%- endif -%}
{%- endmacro %}

{# carrier allowed amount: sum of the 13 line columns #}
{% macro carrier_allowed() -%}
  {%- for j in range(1, 14) -%}
    {{ num('LINE_ALOWD_CHRG_AMT_' ~ j) }}{% if not loop.last %} + {% endif %}
  {%- endfor -%}
{%- endmacro %}

{# whole days from a to b #}
{% macro days_between(a, b) -%}
  {%- if target.type == 'snowflake' -%}
    DATEDIFF(day, {{ a }}, {{ b }})
  {%- else -%}
    DATE_DIFF('day', {{ a }}, {{ b }})
  {%- endif -%}
{%- endmacro %}

{# 4-digit year from a DE-SynPUF file name like DE1_0_2008_Beneficiary_... #}
{% macro file_year(col) -%}
  {%- if target.type == 'snowflake' -%}
    CAST(REGEXP_SUBSTR({{ col }}, 'DE1_0_([0-9]{4})_Beneficiary', 1, 1, 'e', 1) AS INT)
  {%- else -%}
    CAST(REGEXP_EXTRACT({{ col }}, 'DE1_0_([0-9]{4})_Beneficiary', 1) AS INT)
  {%- endif -%}
{%- endmacro %}
