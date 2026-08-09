@echo off
setlocal enabledelayedexpansion

rem List of starting names for CSV files
set "starting_names=output_energydemandstatistics output_exogenous_costs output_model output_technology_costs output_trade_capacity output_other output_annual_production output_capacity output_emission output_production output_costs output_emissions output_fuelcosts output_trade_capacity_new output_technology_costs_detailed output_costs_fuel_breakdown"

rem Directly merge files without a loop
set "merged_file_1=output_energydemandstatistics_merged.csv"
(for %%f in (output_energydemandstatistics*.csv) do @type "%%f" >> !merged_file_1!) && echo Merging for output_energydemandstatistics completed.

set "merged_file_2=output_exogenous_costs_merged.csv"
(for %%f in (output_exogenous_costs*.csv) do @type "%%f" >> !merged_file_2!) && echo Merging for output_exogenous_costs completed.

set "merged_file_3=output_model_merged.csv"
(for %%f in (output_model*.csv) do @type "%%f" >> !merged_file_3!) && echo Merging for output_model completed.

set "merged_file_4=output_technology_costs_merged.csv"
(for %%f in (output_technology_costs*.csv) do @type "%%f" >> !merged_file_4!) && echo Merging for output_technology_costs completed.

set "merged_file_5=output_trade_capacity_merged.csv"
(for %%f in (output_trade_capacity*.csv) do @type "%%f" >> !merged_file_5!) && echo Merging for output_trade_capacity completed.

set "merged_file_6=output_other_merged.csv"
(for %%f in (output_other*.csv) do @type "%%f" >> !merged_file_6!) && echo Merging for output_other completed.

set "merged_file_7=output_annual_production_merged.csv"
(for %%f in (output_annual_production*.csv) do @type "%%f" >> !merged_file_7!) && echo Merging for output_annual_production completed.

set "merged_file_8=output_capacity_merged.csv"
(for %%f in (output_capacity*.csv) do @type "%%f" >> !merged_file_8!) && echo Merging for output_capacity completed.

set "merged_file_9=output_emission_merged.csv"
(for %%f in (output_emission*.csv) do @type "%%f" >> !merged_file_9!) && echo Merging for output_emission completed.

set "merged_file_10=output_production_merged.csv"
(for %%f in (output_production*.csv) do @type "%%f" >> !merged_file_10!) && echo Merging for output_production completed.

set "merged_file_11=output_costs_merged.csv"
(for %%f in (output_costs*.csv) do @type "%%f" >> !merged_file_11!) && echo Merging for output_costs completed.

set "merged_file_12=output_emissions_merged.csv"
(for %%f in (output_emissions*.csv) do @type "%%f" >> !merged_file_12!) && echo Merging for output_emissions completed.

set "merged_file_13=output_fuelcosts_merged.csv"
(for %%f in (output_fuelcosts*.csv) do @type "%%f" >> !merged_file_13!) && echo Merging for output_fuelcosts completed.

set "merged_file_14=output_trade_capacity_new_merged.csv"
(for %%f in (output_trade_capacity_new*.csv) do @type "%%f" >> !merged_file_14!) && echo Merging for output_trade_capacity_new completed.

rem --- Added per your request ---
set "merged_file_15=output_levelizedcosts_merged.csv"
(for %%f in (output_levelizedcosts*.csv) do @type "%%f" >> !merged_file_15!) && echo Merging for output_levelizedcosts completed.

set "merged_file_16=output_materialcosts_merged.csv"
(for %%f in (output_materialcosts*.csv) do @type "%%f" >> !merged_file_16!) && echo Merging for output_materialcosts completed.

set "merged_file_17=output_technology_costs_detailed_merged.csv"
(for %%f in (output_technology_costs_detailed*.csv) do @type "%%f" >> !merged_file_17!) && echo Merging for output_technology_costs_detailed completed.

set "merged_file_18=output_costs_fuel_breakdown_merged.csv"
(for %%f in (output_costs_fuel_breakdown*.csv) do @type "%%f" >> !merged_file_18!) && echo Merging for output_costs_fuel_breakdown completed.
rem --- end added ---

pause
