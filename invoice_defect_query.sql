/*

This query was designed to help identify and prioritize fixes to records 
contributing to a systematic data quality issue, where certain invoices were 
either double-counted or were failing to be counted at all. Because the error 
is bidirectional, the sum of variance was low, since double-countings cancel
out missed countings for the most part; as a result, the team responsible for
this data integrity was having a hard time determining where to start or what
records to look at. To help, I constructed the below query which assesses what
we know of each sales order's processing status to determine the total invoiced 
value we SHOULD have counted, vs invoicing data that shows us what we have
ACTUALLY captured.

The magnitude of the defect varies significantly by day and month, so attached
to each individual analyzed sales item is an accounting of how large of defects
were found on that order date total, and within that order month overall.
Combined with the item's individual variance to expected value, these three
metrics help the data integrity team efficiently prioritize repairs to line
items that will have the most immediate impact for business users once the
record is cleaned up.

Note also that the below is written against the Exasol 7.1 SQL dialect which
is quite distinct (very Oracle-y) and that the below is production code
written against databases that are not very internally-consistent.

-Samuel Garen
206 351 8258
sdgaren@gmail.com

*/


--Pull all sales orders at finest granularity
with sor_cte as (
	select * from (
		select to_date(convert_tz(consumer_order_date_time, 'UTC', 'US/PACIFIC')) as consumer_order_datetime_pacific --Sales order data is stored in UTC, converts to Pacific TZ
			, order_origin
			, netvalue_demand_amt_curr_doc
			, backlog_amt_curr_doc
			, order_qty_uom_sales
			, sor_hdr
			, sor_scl
			, tran_type_ecom
			, country_store
			, sub_brand
			, article
		from nam_analytics.ecom_sor_ohub_nam_tdv --Sales orders on internal eCom channels, e.g. .Com, App, etc.
			
	union all
	
		select to_date(convert_tz(consumer_order_date_time, 'UTC', 'US/PACIFIC')) as consumer_order_datetime_pacific --Sales order data is stored in UTC, converts to Pacific TZ
			, order_origin
			, netvalue_demand_amt_curr_doc
			, backlog_amt_curr_doc
			, order_qty_uom_sales
			, sor_hdr
			, sor_scl
			, tran_type_ecom
			, country_store
			, sub_brand
			, article
		from nam_analytics.marketplace_sor_ohub_nam_tdv --Sales orders on external eCom channels, e.g. Amazon, Instagram, etc.
	)
	
	where sub_brand not in ('16', '11') --Drops Reebok, TaylorMade, etc.
		and tran_type_ecom = 'SL' --Drops SFCC records of consumers creating a return label - these don't count until they turn into an actual invoiced return, which is gathered from the invoice tables themselves
		and country_store = 'US' --Drops other markets
)


--Pull all invoices at finest granularity
, inv_base_cte as (
	
	select * from (
		select * from (
			select * from nam_analytics.ecom_car_ohub_nam_tdv --Invoices from internal eCom channels
			
			union all
			
			select * from nam_analytics.marketplace_car_ohub_nam_tdv --Invoices from external eCom channels
			)
		where invoice_date < '2022-01-01' --Invoice dates are stored in PST/PDT and do not need to be converted
			and upper(omnichannel_tran_type) in ('H','A','I','Y','E','P') --Pre-2022 P&L is based on mechanism of fulfillment; filters for orders fulfilled by distribution center network and not by shipments / pickups from Retail stores
		
		union all
		
		select * from (
			select * from nam_analytics.ecom_car_ohub_nam_tdv --Invoices from internal eCom channels
			
			union all
			
			select * from nam_analytics.marketplace_car_ohub_nam_tdv --Invoices from external eCom channels
		)
		where invoice_date >= '2022-01-01' --Invoice dates are stored in PST/PDT and do not need to be converted
			and upper(order_origin) != 'ENDLESS AISLE' --2022-forward P&L is based on order origination; Endless Aisle is considered Retail origination, even though order is fulfilled from distribution center network
	)
	
	where upper(brand_descr) like '%ADIDAS%' --Drops Reebok, TaylorMade, etc.
		and upper(country_store) = 'US' --Drops other markets
)


--Aggregate invoices up to order header / line-item level to account for the fact that there is a one-to-many relationship between sales orders and invoices that will make a mess of the later join if invoices are not aggregated up
, inv_agg_cte as (
	select sor_hdr
		, sor_scl		
		, sum(netsales_ex_vat_amt_curr_loc) as net_sales_val --Total net sales amount excluding tax
		, sum(
			case when upper(tran_type_sales) = 'SL' then netsales_ex_vat_amt_curr_loc
				else 0
			end
			) as delivered_val --Total of outbound invoice values for this order / line item
		, sum(
			case when upper(tran_type_sales) = 'RT' then netsales_ex_vat_amt_curr_loc
				else 0
			end
			) as returned_val --Total of return invoice values for this order / line item
	from inv_base_cte

	group by 1,2
)


--Join sales orders and invoices, calculate variance between what the invoice table SHOULD show and what it ACTUALLY shows per row. Elevate the months, dates within, and items within with the greatest value of variance. Data Integrity will prioritize research in the order this report returns.
select sor_cte.sor_hdr as 'Order Header'
	, sor_cte.sor_scl as 'Line Item'
	, sor_cte.consumer_order_datetime_pacific as 'Order Date PST/PDT' --Order datetimes are stored in UTC, converts to Pacific timezone
	, sor_cte.order_origin as 'Order Origin'
	, sor_cte.article as 'Article'
	, sor_cte.netvalue_demand_amt_curr_doc as 'Sales Order Value'
	, sor_cte.backlog_amt_curr_doc as 'Fulfillment Backlog Value'
	, coalesce(inv_agg_cte.delivered_val, 0) as 'Delivered Value'
	, coalesce(inv_agg_cte.returned_val, 0) as 'Returned Value'
	, sor_cte.netvalue_demand_amt_curr_doc - sor_cte.backlog_amt_curr_doc + coalesce(inv_agg_cte.returned_val, 0) as 'Expected Net Sales Value'
	, coalesce(inv_agg_cte.net_sales_val, 0) as 'Actual Net Sales Value'
	, coalesce(inv_agg_cte.net_sales_val, 0) - (sor_cte.netvalue_demand_amt_curr_doc - sor_cte.backlog_amt_curr_doc + coalesce(inv_agg_cte.returned_val, 0)) as 'Variance, Net Sales to Expected Net Sales'
	, sum(coalesce(inv_agg_cte.net_sales_val, 0) - (sor_cte.netvalue_demand_amt_curr_doc - sor_cte.backlog_amt_curr_doc + coalesce(inv_agg_cte.returned_val, 0))) over (partition by sor_cte.consumer_order_datetime_pacific) as 'Total Variance on Order Date'
	, sum(coalesce(inv_agg_cte.net_sales_val, 0) - (sor_cte.netvalue_demand_amt_curr_doc - sor_cte.backlog_amt_curr_doc + coalesce(inv_agg_cte.returned_val, 0))) over (partition by trunc(sor_cte.consumer_order_datetime_pacific, 'MM')) as 'Total Variance in Order Month'
from sor_cte

left join inv_agg_cte on inv_agg_cte.sor_hdr = sor_cte.sor_hdr and inv_agg_cte.sor_scl = sor_cte.sor_scl

where sor_cte.consumer_order_datetime_pacific >= add_years(to_date(convert_tz(systimestamp, 'EUROPE/BERLIN', 'US/PACIFIC')), -1) --Report covers rolling one year
	and coalesce(inv_agg_cte.net_sales_val, 0) - (sor_cte.netvalue_demand_amt_curr_doc - sor_cte.backlog_amt_curr_doc + coalesce(inv_agg_cte.returned_val, 0)) != 0 --Only return rows where some variance / defect is found
	
order by 14 desc, 13 desc, 12 desc
;