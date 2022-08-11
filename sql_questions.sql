/* Please find below the answers to the six SQL coding questions found in the assessment. The below is written against the MS SQL Server 2017 dialect.

-Samuel Garen
206 351 8258
sdgaren@gmail.com
*/



--Question 2

select count(distinct(customer_id)) --Since we only have a sample of the data and can't perform EDA on the full dataset, for safety we will assume customers may be allowed to have multiple subscriptions with overlapping dates and thus count distinct customer_ids as our count of customers per date.
from plan_history
where cast(plan_start as date) <= '2016-01-01'
  and (plan_end > '2016-01-01' or plan_end is null) --Treats plan_end exactly at 00:00 of a given date as not active on that date, but plan_end after 00:00 as having been active on that date; e.g. 3488 is not active on 1/28/2016, but 2231 is active on 7/18/2016.



--Question 3

select d.dte as 'Date'
  , count(distinct(ph.customer_id)) as 'Count of Customers' --Assumes the same customer_id may be associated with multiple overlapping subscriptions as in question 2.
from plan_history as ph

inner join all_dates as d on d.dte >= cast(ph.plan_start as date)
  and d.dte < coalesce(ph.plan_end, getdate()) --Treats plan_end exactly at 00:00 of a given date as not active on that date, but plan_end after 00:00 as active. Assumes you don't want reporting out to 2030 and trims the report to end at current date for all customer_ids with no plan_end entered (e.g., assumes these are still active). Timezone conversion of plan_start, plan_end, and getdate() may be needed depending on user needs and what timezone these timestamps are stored in.

group by dte
order by dte



--Question 4

select c.city as 'City' --Unless this is really a city + state field, would caution users that two different cities with the same name (Portland, OR and Portland, ME) will be added together, since there is no explicit state field to distinguish them. If needed, could use the postal_code field to derive state, either mapped from the first two digits of the postal code or by joining postal code one of the datasets the USPS publishes.
  , coalesce(sum(i.amount), 0) as 'Total Sales' --This coalesce and the left join below assume the user would like to see cities that exist in the customer database but do not have any invoices against them yet. Remove coalesce and convert to inner join if cities only with invoices is the requirement.

from customer as c

left join invoice as i on i.customer_id = c.id

group by c.city
order by coalesce(sum(i.amount), 0) desc, c.city



--Question 5

select c.city as 'City' --Same notes as for question four, but perhaps even more acute here, since if Portland, OR generated $50,001 and Portland, ME generated $50,000, they might appear in this report together on the same row if they are both listed just as "Portland", since together they have generated >$100,000 and will pass through the "having" clause.
  , sum(i.amount) as 'Total Sales' --Coalese is no longer useful if cities without invoices will not appear in the report.

from customer as c

left join invoice as i on i.customer_id = c.id

group by c.city

having sum(i.amount) > 100000

order by sum(i.amount) desc, c.city



--Question 6

select c.name as 'Customer Name'
  , c.credit_limit as 'Credit Limit'
  , a.amount as 'Amount of First Invoice' --Here we assume that the user would like to see customers even if they haven't generated an invoice yet. We do not coalesce this value, since at customer-level, the user might find it useful to know if a customer hasn't generated an invoice yet (null value) vs if the customer has generated an invoice for zero value (such as if they purchased and were refunded for a product, or their first invoice is otherwise extant but of zero total value for one reason or another).
from customer as c

left join ( 
  select i.customer_id
    , i.amount
  from invoice as i
  
  inner join
  
  (select customer_id
  , min(created_at) as created_at
  from invoice
   
  group by customer_id)
  
  as f on i.created_at = f.created_at and i.customer_id = f.customer_id
) as a

on c.id = a.customer_id



--Question 7

--The below CTE assumes that the all_dates table is still available to us from question 3. Here, we build a sequential list of months and years within the relevant date range of the report. This ensures that even if we have no invoicing activity for a given month that said month still appears in our report output - the YTD invoice amount won't go up from the month before it of course, but the fact that it did not increment is also useful information.
with invoice_cte as (
  select year(d.dte) as invoice_year --Invoice month and year are broken into separate fields for ease of summation / pivoting in Excel, where all financial reporting seems to ultimately end up. This could be composed as a date string showing the first day of the month instead using the "datefromparts" function in MS SQL Server dialect or "datetrunc" function in Oracle-influenced dialects.
    , month(d.dte) as invoice_month
    , coalesce(sum(i.amount), 0) as total_invoice_amount
  from all_dates as d

  left join invoice as i on i.created_at = d.dte

  where d.dte >= (select min(created_at) from invoice) --Start the report's range in the month where the first invoice is counted; no need to have from 2010 forward if the invoices we are interested in start in 2020, for example.
    and d.dte <= getdate() --End the report's range at the current month so the report doesn't extend to 2030 with a bunch of zero-value rows.

  group by year(d.dte), month(d.dte)
)

select invoice_year as 'Invoice Year'
  , invoice_month as 'Invoice Month'
  , sum(total_invoice_amount) over (partition by invoice_year order by invoice_year, invoice_month) as 'YTD Invoice Amount'
from invoice_cte