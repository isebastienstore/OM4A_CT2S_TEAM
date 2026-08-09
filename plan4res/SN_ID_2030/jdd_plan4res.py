# -*- coding: utf-8 -*-
"""
Created on Tue Jun 11 11:26:55 2024

@author: Thomas Ouillon @EDF
"""
__version__ = '0.4'

import datetime
import numpy as np
import os
import os.path as osp
import pandas as pd
import re
import yaml

from plotly import express as px
import plotly.graph_objects as go

import logging
logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

input_names = {
               'Annual' : 'IAMC_annuel_data.csv',
               'IN'     : 'IN_Interconnections.csv',
               'RES'    : 'RES_RenewableUnits.csv',
               'SS'     : 'SS_SeasonalStorage.csv',
               'STS'    : 'STS_ShortTermStorage.csv',
               'TU'     : 'TU_ThermalUnits.csv',
               'ZP'     : 'ZP_ZonePartition.csv',
               'ZV'     : 'ZV_ZoneValues.csv'
               }
       
def all_levels_but(levels, but):
    if not isinstance(but, list):
        but = [but]
    return [l for l in levels if l not in but]
    
def style_graph(h, w):
    return dict(height=h, width=w, plot_bgcolor='white', legend_font_size=16, xaxis_tickfont_size=16, yaxis_tickfont_size=16, xaxis_title_font_size=16, yaxis_title_font_size=16)
  
def hex_to_rgba(h, opacity):
    if h.startswith('#'):
        h=h.lstrip('#')
        return 'rgba('+','.join(str(int(h[i:i+2], 16)) for i in (0, 2, 4))+f',{opacity})'
    elif h.startswith('rgb'):
        return  h[:-1]+f',{opacity})'  

class JDDP4R:
    def __init__(self, data_dir, year, settings_dir=None, simul_results_dir=None):
        if settings_dir is None:
            settings_dir = osp.join(data_dir, 'settings')
        self.data_dir = data_dir
        self.name = osp.basename(self.data_dir.strip('/'))
        self.load_setting(settings_dir)
        self.year = year
        
        self.stochastic_scenarios = self.settingsCreateInputPlan4res['StochasticScenarios']
        self.regions = self.settingsCreateInputPlan4res['partition']['Region']
        self.iamc_dir = osp.join(self.data_dir, self.settingsLinkageGENeSYS['outputpath'] if 'outputpath' in self.settingsLinkageGENeSYS in keys() else 'IAMC')
        self.input_dir = osp.join(self.data_dir, self.settingsCreateInputPlan4res['outputpath'])
        logger.info('Read input from '+self.input_dir)
        self.interconnections    = pd.read_csv(osp.join(self.input_dir, input_names['IN']), index_col=0)
        self.renewables          = pd.read_csv(osp.join(self.input_dir, input_names['RES']), index_col=[0, 1])
        self.seasonal_storages   = pd.read_csv(osp.join(self.input_dir, input_names['SS']), index_col=[0, 1])
        self.short_term_storages = pd.read_csv(osp.join(self.input_dir, input_names['STS']), index_col=[0, 1])
        self.thermal_units       = pd.read_csv(osp.join(self.input_dir, input_names['TU']), index_col=[1, 0])
        self.thermal_units.index = self.thermal_units.index.set_levels(self.thermal_units.index.levels[0].str.replace('Electricity|',''), level=0)
        self.zone_partitions     = pd.read_csv(osp.join(self.input_dir, input_names['ZP']), index_col=0)
        self.zone_values         = pd.read_csv(osp.join(self.input_dir, input_names['ZV']), index_col=[0, 1])
        self.capacities = pd.concat([self.renewables['MaxPower'], self.seasonal_storages['MaxPower'], self.short_term_storages['MaxPower'], self.thermal_units['MaxPower']])
        self.zones = self.zone_values.loc['Total'].index
        self.calendar = pd.date_range(datetime.datetime(year,1,1), datetime.datetime(year,12,30,23), freq='H')
        self.timeseries = pd.DataFrame()
        self.simul_results_dir = simul_results_dir if simul_results_dir is not None else osp.join(self.data_dir, 'results_simul')
        
    def load_setting(self, setting_dir):
        self.setting_dir = setting_dir
        def _read_setting(s):
            tag = s[:-4]
            f = osp.join(setting_dir, s)
            setattr(self, f'_file_{tag}', f)
            if osp.isfile(f):
                logger.info('Reading '+f)
                with open(f) as _:
                    setattr(self, f'{tag}', yaml.load(_,Loader=yaml.FullLoader))
        for f in os.listdir(setting_dir):
            if f.endswith('.yml') and f.startswith('settings'):
                _read_setting(f)
                
    def load_genesys_data(self, detailed_data=True):
        if 'genesys_inputpath' not in self.settingsLinkageGENeSYS.keys(): 
            self.gen_input_dir = osp.join(self.data_dir, 'GENeSYS-MOD', 'inputs')
        if 'genesys_resultspath' not in self.settingsLinkageGENeSYS.keys(): 
            self.gen_output_dir = osp.join(self.data_dir, 'GENeSYS-MOD', 'outputs')
        self.input_xlsx = osp.join(self.settingsLinkageGENeSYS['genesys_datafiles']['input']['inputfile'])
        self.scenario = self.settingsLinkageGENeSYS['Scenario']
        self.scenarios_from_genesys = self.settingsLinkageGENeSYS['Scenarios'][self.scenario]
        def _read_ouput(f):
            logger.info('Read '+osp.join(self.gen_output_dir,f))
            res = pd.read_csv(osp.join(self.gen_output_dir,f))
            return res.set_index(all_levels_but(res.columns, 'Value'))
        for k,f in self.settingsLinkageGENeSYS['genesys_datafiles']['output'].items():
            setattr(self, f'genesysmod_{k}', _read_ouput(f))
        if detailed_data:
            if 'timeseries_production' not in self.settingsLinkageGENeSYS['genesys_datafiles']['output'].keys():
                logger.warning('Detailed data requested: please add tag "genesys_datafiles>output>timeseries_production" in file '+self._file_settingsLinkageGENeSYS)
            else:
                setattr(self, 'genesysmod_timeseries_production', _read_ouput(self.settingsLinkageGENeSYS['genesys_datafiles']['output']['timeseries_production']))
                setattr(self, 'genesysmod_timeseries_production_yearsum', self.genesysmod_timeseries_production.groupby(level=all_levels_but(self.genesysmod_timeseries_production.index.names, 'Timeslice')).sum())
        self._mapping_technos = pd.Series({k:self.settingsLinkageGENeSYS['TechnosMappings'][k]['TechnoIAMC'] for k in  self.settingsLinkageGENeSYS['TechnosMappings']})
        self._mapping_storages = pd.Series({k:self.settingsLinkageGENeSYS['StorageMappings'][k]['TechnoIAMC'] for k in  self.settingsLinkageGENeSYS['StorageMappings']})
        self._mapping_storages.index = self._mapping_storages.index.map(lambda _ : re.sub('^D_','P_', _))
        self.mapping_gen_to_p4r = pd.concat([self._mapping_technos, self._mapping_storages])
        self.mapping_p4r_to_gen = pd.Series({v:k for k,v in self.mapping_gen_to_p4r.items()})
        
    def load_iamc_data(self):
        self.iamc_data = pd.read_csv(osp.join(self.iamc_dir, self.name+'.csv'),index_col=['Region','Unit','Scenario','Year','Variable','Model'])
    
    def compare_genmod_and_p4r_capacity(self, comparison_file=None):
        self.compare_capacity = (1e3*self.genesysmod_capacity.loc[(slice(None), ['Power','Storages'], slice(None), 'TotalCapacity', self.scenarios_from_genesys, self.year),'Value'].groupby(level=all_levels_but(self.genesysmod_capacity.index.names, 'PathwayScenario')).sum().droplevel([1,3,4])).to_frame('Capacity GENeSYS-MOD (MW)')
        self.compare_capacity.index = self.compare_capacity.index.remove_unused_levels()
        self.compare_capacity['Name in GENeSYS-MOD'] = self.compare_capacity.index.get_level_values('Technology')
        self.compare_capacity.index = self.compare_capacity.index.set_levels(self.compare_capacity.index.levels[1].map(self.mapping_gen_to_p4r).str.replace('Electricity|',''), level=1)
        self.compare_capacity = pd.concat([self.compare_capacity, self.capacities.swaplevel().to_frame('Capacity in Plan4Res (MW)')], axis=1)
        self.compare_capacity['Name in Plan4Res'] = self.compare_capacity.index.get_level_values(1)
        self.compare_capacity = self.compare_capacity[['Name in GENeSYS-MOD', 'Capacity GENeSYS-MOD (MW)', 'Name in Plan4Res', 'Capacity in Plan4Res (MW)']].sort_index()
        if comparison_file is not None:
            self.compare_capacity.to_excel(comparison_file)
            
    def compute_renewables_yearly_available_energy(self):
        self.yearly_available_energy_res = self.timeseries.sum().unstack(level=2).multiply(self.renewables['Capacity'],axis=0)/1e3 # GWh
        #self.available_and_produced_energy = 
        
    
    def compare_genmod_and_p4r_generation(self, comparison_file=None):
        if not hasattr(self, 'generation'):
            self.read_generation()
        def treat(generation_from_genesys, tag):
            _generation = self.genesysmod_annual_production.loc[(slice(None), ['Power','Storages'], slice(None), 'Power', ['Production', 'Use'], slice(None), self.scenarios_from_genesys, self.year),'Value'].groupby(level=all_levels_but(self.genesysmod_annual_production.index.names, 'PathwayScenario')).sum().droplevel([1,3,5,6]).to_frame(tag)
            _generation /= 3.6e-3 # from PJ to GWh
            _generation.index = _generation.index.remove_unused_levels()
            _generation.index = _generation.index.set_levels(_generation.index.levels[1].map(self.mapping_gen_to_p4r).str.replace('Electricity|',''), level=1)
            _generation['Name in Plan4Res'] = [_generation.index.get_level_values(1)[i]+('_PUMP' if _generation.index.get_level_values(2)[i] == 'Use' else '') for i in range(_generation.shape[0])]
            _generation.set_index('Name in Plan4Res', append=True, inplace=True)
            _generation = _generation.droplevel(['Type', 'Technology'])
            return _generation
        genmod_generation = treat(self.genesysmod_annual_production, 'Generation GENeSYS-MOD (GWh)')
        genmod_generation_yearsum = treat(self.genesysmod_timeseries_production_yearsum, 'Generation GENeSYS-MOD year sum (GWh)')
        gen_p4r = self.generation.sum().unstack(level=1)/1e3 # GWh
        gen_p4r.columns = 'Generation in Plan4Res - scenario '+gen_p4r.columns.astype(str)
        idx = genmod_generation.index.intersection(gen_p4r.index)
        self.compare_generation = pd.concat([genmod_generation.loc[idx], genmod_generation_yearsum.loc[idx], gen_p4r.loc[idx]], axis=1)
        #self.compare_generation = self.compare_generation[['Name in GENeSYS-MOD', 'Generation GENeSYS-MOD (GWh)', 'Name in Plan4Res']+[c for c in self.compare_generation.columns if 'Plan4Res' in c and 'scenario' in c]].sort_index()
        if comparison_file is not None:
            self.compare_generation.to_excel(comparison_file)
                
    def rename_col(self, c, sep='_'):
        z = sorted([_ for _ in self.zone_partitions.index if _ in c], key=len)[-1]
        return (z, c.replace(z, '').strip(sep))
        
    def read_generation(self):
        if hasattr(self, 'generation'):
            return
        rep = osp.join(self.simul_results_dir, 'ActivePower')
        logger.info('Read generation in '+rep)
        self.generation = dict()
        for zone in self.zone_partitions.index:
            logger.info('\tFor '+zone)
            files = [f for f in os.listdir(rep) if f.startswith('Generation-'+zone) and f.endswith('.csv')]
            generation_zone = dict()
            for f in files:
                scenario = self.stochastic_scenarios[int(f[:-4].split('-')[-1])]
                logger.info('\t\tRead '+f)
                generation_zone[scenario] = pd.read_csv(osp.join(rep, f), index_col=0)
            self.generation[zone] = pd.concat(generation_zone, axis=1)
        self.generation = pd.concat(self.generation, axis=1).sort_index(axis=1)
        self.generation.index = self.calendar
        print(self.generation)
        
    def read_active_power(self):
        if hasattr(self, 'active_power'):
            return
        rep = osp.join(self.simul_results_dir, 'ActivePower')
        logger.info('Read active power in '+rep)
        self.active_power = dict()
        fichiers = [f for f in os.listdir(rep) if f.startswith('ActivePower') and f.endswith('.csv')]
        for f in fichiers:
            scenario = self.stochastic_scenarios[int(re.search('Scen(\d+)_OUT', f).group(1))]
            logger.info('\tRead '+f)
            self.active_power[scenario] = pd.read_csv(osp.join(rep, f), index_col=0)
            self.active_power[scenario].columns = pd.MultiIndex.from_tuples([self.rename_col(c) for c in self.active_power[scenario].columns])
        self.active_power = pd.concat(self.active_power, axis=1).swaplevel(0, 1, axis=1).sort_index(axis=1)
        self.active_power.index = self.calendar
        
    def read_max_power(self):
        if hasattr(self, 'max_power'):
            return
        rep = osp.join(self.simul_results_dir, 'MaxPower')
        logger.info('Read max power in '+rep)
        self.max_power = dict()
        fichiers = [f for f in os.listdir(rep) if f.startswith('MaxPower') and f.endswith('.csv')]
        for f in fichiers:
            scenario = self.stochastic_scenarios[int(re.search('Scen(\d+)_OUT', f).group(1))]
            logger.info('\tRead '+f)
            self.max_power[scenario] = pd.read_csv(osp.join(rep, f), index_col=0)
            self.max_power[scenario].columns = pd.MultiIndex.from_tuples([self.rename_col(c) for c in self.max_power[scenario].columns])
        self.max_power = pd.concat(self.max_power, axis=1).swaplevel(0, 1, axis=1).sort_index(axis=1)
        self.max_power.index = self.calendar
        
    def read_demand(self, areas=None, scenarios=None):
        if hasattr(self, 'demand'):
            return
        rep = osp.join(self.simul_results_dir, 'Demand')
        logger.info('Read demand in : '+rep)
        self.demand = dict()
        files = [f for f in os.listdir(rep) if f.startswith('Demand') and f.endswith('.csv') and 'Scen' in f]
        for f in files:
            scenario = self.stochastic_scenarios[int(re.search('Scen(\d+)_OUT', f).group(1))]
            logger.info('\tRead '+f)
            self.demand[scenario] = pd.read_csv(osp.join(rep, f), index_col=0)
        self.demand = pd.concat(self.demand, axis=1).swaplevel(0, 1, axis=1).sort_index(axis=1)
        self.demand.index = self.calendar
        self.yearly_total_demand = self.demand.sum().unstack(level=1)
        
    def read_primary(self):
        if hasattr(self, 'primary'):
            return
        rep = osp.join(self.simul_results_dir, 'Primary')
        logger.info('Read primary in '+rep)
        self.primary = dict()
        files = [f for f in os.listdir(rep) if f.startswith('Primary') and f.endswith('.csv')]
        for f in files:
            scenario = int(f[7:-4].split('-')[-1])
            logger.info('\tRead '+f)
            self.primary[scenario] = pd.read_csv(osp.join(rep, f), index_col=0)
            self.primary[scenario].columns = pd.MultiIndex.from_tuples([self.rename_col(c) for c in self.primary[scenario].columns])
        self.primary = pd.concat(self.primary, axis=1).swaplevel(0, 1, axis=1).swaplevel(1, 2, axis=1).sort_index(axis=1)
        self.primary.index = self.calendar
        
    def read_secondary(self):
        if hasattr(self, 'secondary'):
            return
        rep = osp.join(self.simul_results_dir, 'Secondary')
        logger.info('Read secondary in '+rep)
        self.secondary = dict()
        files = [f for f in os.listdir(rep) if f.startswith('Secondary') and f.endswith('.csv')]
        for f in files:
            scenario = int(f[9:-4].split('-')[-1])
            logger.info('\tRead '+f)
            self.secondary[scenario] = pd.read_csv(osp.join(rep, f), index_col=0)
            self.secondary[scenario].columns = pd.MultiIndex.from_tuples([self.rename_col(c) for c in self.secondary[scenario].columns])
        self.secondary = pd.concat(self.secondary, axis=1).swaplevel(0, 1, axis=1).swaplevel(1, 2, axis=1).sort_index(axis=1)
        self.secondary.index = self.calendar

    def read_flows(self):
        if hasattr(self, 'flows'):
            return
        rep = osp.join(self.simul_results_dir, 'Flows')
        logger.info('Read flows in '+rep)
        self.flows = dict()
        files = [f for f in os.listdir(rep) if f.startswith('Flows') and f.endswith('.csv')]
        for f in files:
            scenario = self.stochastic_scenarios[int(re.search('Scen(\d+)_OUT', f).group(1))]
            logger.info('\tRead '+f)
            self.flows[scenario] = pd.read_csv(osp.join(rep, f), index_col=0)
        self.flows = pd.concat(self.flows, axis=1).swaplevel(0, 1, axis=1).sort_index(axis=1)
        self.exports = {z : dict() for z in self.zones}
        self.imports = {z : dict() for z in self.zones}
        for c in self.flows.columns.levels[0]:
            start_zone, end_zone = c.split('>')
            self.exports[start_zone][end_zone] = -np.maximum(self.flows[c], 0)
            self.imports[start_zone][end_zone] = -np.minimum(self.flows[c], 0)
            self.exports[end_zone][start_zone] = -np.maximum(-self.flows[c], 0)
            self.imports[end_zone][start_zone] = -np.minimum(-self.flows[c], 0)
        self.exports = pd.concat({z : pd.concat(e, axis=1) for z,e in self.exports.items()},axis=1).sort_index(axis=1)
        self.exports.columns.names = ['Exporting zone', 'Importing zone', 'Scenario']
        self.imports = pd.concat({z : pd.concat(i, axis=1) for z,i in self.imports.items()},axis=1).sort_index(axis=1)
        self.imports.columns.names = ['Importing zone', 'Exporting zone', 'Scenario']
        self.exports.index = self.calendar
        self.imports.index = self.calendar
        
    def read_marginal_costs(self):
        if hasattr(self, 'marginal_cost'):
            return
        rep = osp.join(self.simul_results_dir, 'MarginalCosts')
        logger.info('Read marginal costs in '+rep)
        self.marginal_costs = dict()
        for const in ['ActivePowerDemand', 'Flows', 'Inertia', 'Primary', 'Secondary']:
            logger.info('\tFor '+const)
            marginal_cost = dict()
            files = [f for f in os.listdir(rep) if f.startswith('MarginalCost'+const) and f.endswith('.csv')]
            for f in files:
                try:
                    scenario = int(f[len(f'MarginalCost{const}_Scen'):-4].replace('_OUT',''))
                except:
                    continue 
                logger.info('\t\tRead '+f)
                marginal_cost[scenario] = pd.read_csv(osp.join(rep, f), index_col=0)
                if len(marginal_cost)>0:
                    self.marginal_costs[const] = pd.concat(marginal_cost, axis=1)
                else:
                    self.marginal_costs[const] = pd.DataFrame()
        if len(self.marginal_costs) > 0:
            self.marginal_costs = pd.concat(self.marginal_costs, axis=1).swaplevel(1, 2, axis=1).sort_index(axis=1)
            self.marginal_costs.index = self.calendar
        else:
            self.marginal_costs = pd.DataFrame()
    
    def read_volumes(self):
        if hasattr(self, 'volumes'):
            return
        rep = osp.join(self.simul_results_dir, 'Volume')
        logger.info('Read volumes in '+rep)
        self.volumes = dict()
        files = [f for f in os.listdir(rep) if f.startswith('Volume') and f.endswith('.csv')]
        for f in files:
            if 'OUT' in f:
                try:
                    scenario = self.stochastic_scenarios[int(f[11:-8])]
                except:
                    continue
                logger.info('\tRead '+f)
                self.volumes[scenario] = pd.read_csv(osp.join(rep, f), index_col=0)
                self.volumes[scenario].columns = pd.MultiIndex.from_tuples([self.rename_col(c) for c in self.volumes[scenario].columns])
        self.volumes = pd.concat(self.volumes, axis=1).swaplevel(0, 1, axis=1).sort_index(axis=1)
        self.volumes.index = self.calendar
        
    def read_bellman_values(self):
        bvout_file = osp.join(self.simul_results_dir, 'BellmanValuesOUT.csv')
        if osp.isfile(bvout_file):
            self.bv_out = pd.read_csv(bvout_file)
        cuts_file = osp.join(self.simul_results_dir, 'cuts.txt')
        if osp.isfile(cuts_file):
            self.cuts = pd.read_csv(cuts_file)
            
    def read_slack(self):
        if hasattr(self, 'slack'):
            return
        logger.info('Read slack information')
        self.slack = dict()
        for r in self.regions:
            p = osp.join(self.simul_results_dir, 'OUT', f'Slack-{r}.csv')
            logger.info('Reading '+p)
            self.slack[r] = pd.read_csv(p, index_col=0)
            self.slack[r].columns = self.stochastic_scenarios
        self.slack = pd.concat(self.slack,axis=1)
        self.year_total_slack = self.slack.sum().unstack(level=1)
        
    def read_simul_output(self):
        try:
            self.read_generation()
        except:
            logger.warning('Error while reading generation')
        try:
            self.read_active_power()
        except:
            logger.warning('Error while reading active power')
        try:
            self.read_flows()
        except:
            logger.warning('Error while reading flows')
        try:
            self.read_max_power()
        except:
            logger.warning('Error while reading max power')
        try:
            self.read_demand()
        except: 
            logger.warning('Error while reading demand')
        try:
            self.read_primary()
        except:
            logger.warning('Error while reading primary')
        try:
            self.read_secondary()
        except:
            logger.warning('Error while reading secondary')
        try:
            self.read_marginal_costs()
        except:
            logger.warning('Error while reading marginal costs')
        try:
            self.read_volumes()
        except:
            logger.warning('Error while reading volumes')
        try:
            self.read_slack()
        except:
            logger.warning('Error while reading slack')
            
    def get_stacked_prod(self, area, scenario):
        if not hasattr(self,'demand'):
            self.read_demand()
        load = self.demand[(area, scenario)]
        if not hasattr(self,'generation'):
            self.read_generation()
        gen = self.generation[(area, scenario)]
        self.read_flows()
        imports = self.imports.loc[:, (area, slice(None), scenario)].droplevel([0,2], axis=1)
        exports = self.exports.loc[:, (area, slice(None), scenario)].droplevel([0,2], axis=1)
        imports.columns = 'Import - '+imports.columns
        exports.columns = 'Export - '+exports.columns
        stack_prod = pd.concat([gen, imports, exports],axis=1)
        return pd.concat({'Load':load.to_frame('Load'), 'Stack' : stack_prod}, axis=1)
        
    def read_timeseries(self, rep, struct_data):
        timeseries = dict()
        for i,f in struct_data.items():
            p = osp.join(rep, f)
            if not osp.isfile(p):
                logger.warning(p+' does not exist.')
                continue
            logger.info('Read '+p)
            timeseries[i] = pd.read_csv(p, index_col=0, parse_dates=True, dayfirst=True)
        self.timeseries = pd.concat([self.timeseries, pd.concat(timeseries,axis=1)], axis=1)
        
    def _get_color_map_for_prod(self, columns):
        colors = pd.DataFrame(self.settingsPostTreatPlan4res['Technos']).loc['color'].to_dict()
        colors['Load'] = 'grey'
        colors['Load + export'] = 'darkgrey'
        import_cols = [c for c in columns if c.startswith('Import')]
        export_cols = [c for c in columns if c.startswith('Export')]
        colorscale = [
                        [0.0, '#DDA0DD'],   # plum
                        [1.0, '#4B0082'],   # indigo
                     ]
        connected_areas = set(_.replace('Import - ','') for _ in import_cols).union(set(_.replace('Export - ','') for _ in export_cols))
        colors_exchange = {c:px.colors.sample_colorscale(colorscale, i/(max(len(import_cols),len(export_cols))))[0] for i,c in enumerate(connected_areas)}
        colors.update({'Import - '+c : colors_exchange[c] for c in colors_exchange.keys()})
        colors.update({'Export - '+c : colors_exchange[c] for c in colors_exchange.keys()})
        for c in columns:
            if not c in colors.keys():
                colors[c] = 'darkgrey'
        colors['SlackUnit']='rgb(255,0,0)'
        return {c:colors[c] for c in columns.tolist()+['Load','Load + export']}
        
    def plot_bar_plot_year(self, result_directory):
        if not osp.isdir(result_directory):
            os.makedirs(result_directory)
        for r in self.regions:
            logger.info(f'Plotting yearly data for region {r}.') 
            fig=go.Figure()
            data = pd.concat({s:self.get_stacked_prod(r,s).sum() for s in self.stochastic_scenarios})/1e3 # GWh
            data_prod = data.drop('Load',level=1).droplevel(1)
            color_map = self._get_color_map_for_prod(data_prod.index.levels[1])
            data_prod = data_prod.reset_index()
            data_prod.columns = ['Scenario', 'Techno', 'Generation (GWh)']
            data_load = data.loc[(slice(None),'Load')].droplevel(1).reset_index()
            data_load.columns = ['Scenario', 'Load (GWh)']
            fig=px.bar(data_prod, x='Scenario',y='Generation (GWh)', color='Techno', color_discrete_map=color_map, text_auto='.1f')
            fig.add_trace(go.Scatter(x=data_load['Scenario'],y=data_load['Load (GWh)'], mode='markers', marker=dict(color=color_map['Load'],size=8), name='Load'))
            fig=fig.update_layout(style_graph(1200,2000), title=f'Yearly generation {r}', title_font_size=24, uniformtext_minsize=24, uniformtext_mode='hide', legend=dict(font=dict(size=22)))
            fig=fig.update_annotations(font_size=24)
            fig=fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[1]))
            fig=fig.update_xaxes(showline=True, linewidth=2, linecolor='black', mirror=True, zeroline=True, zerolinewidth=1, zerolinecolor='grey', tickfont_size=20)
            fig=fig.update_yaxes(title='GWh', showgrid=True, gridwidth=1, zeroline=False, gridcolor='grey', showline=True, linewidth=2, linecolor='black', mirror=True, tickfont_size=20, title_font_size=24)
            fig.write_html(osp.join(result_directory, f'yearly_generation_{r.replace(r"|","-")}.html'))
    
    def plot_all_stacked_plots(self, result_directory, opacity=0.7):
        if not osp.isdir(result_directory):
            os.makedirs(result_directory)
        for r in self.regions:
            for s in self.stochastic_scenarios:
                fig=go.Figure()
                logger.info(f'Plotting scenario {s} for region {r}.') 
                stacked = self.get_stacked_prod(r,s)
                gen_and_import = stacked['Stack']
                color_map = self._get_color_map_for_prod(gen_and_import.columns)
                prod_pos = [c for c in gen_and_import.columns if (gen_and_import[c] > 0).any()]
                prod_pos = [c for c in prod_pos if 'solar' in c.lower() or 'wind' in c.lower()]+[c for c in prod_pos if 'solar' not in c.lower() and 'wind' not in c.lower()] # plot ENRv first
                prod_neg = [c for c in gen_and_import.columns if (gen_and_import[c] < 0).any()]
                prod_neg = [c for c in prod_neg if 'solar' in c.lower() or 'wind' in c.lower()]+[c for c in prod_neg if 'solar' not in c.lower() and 'wind' not in c.lower()] # plot ENRv first
                for c in prod_pos:
                    fig.add_trace(go.Scatter(x=gen_and_import.index, y=np.maximum(0, gen_and_import[c]), fill='tonexty', fillcolor=color_map[c],
                                   mode='lines', line=dict(width=0, color=hex_to_rgba(color_map[c], opacity)), name=c, stackgroup='prod_pos', showlegend=True))
                for c in prod_neg:
                    fig.add_trace(go.Scatter(x=gen_and_import.index, y=np.minimum(0, gen_and_import[c]), fill='tonexty', fillcolor=color_map[c],
                                   mode='lines', line=dict(width=0, color=hex_to_rgba(color_map[c], opacity)), name=c, stackgroup='prod_neg', showlegend=True))
                fig.add_trace(go.Scatter(x=stacked.index,y=stacked[('Load','Load')], line_color=color_map['Load'], line_width=2, name='Load'))
                fig=fig.update_layout(style_graph(1200,2000), title=f'Generation {r} for scenario {s}', title_font_size=24, uniformtext_minsize=24, uniformtext_mode='hide', legend=dict(font=dict(size=22)))
                fig=fig.update_annotations(font_size=24)
                fig=fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[1]))
                fig=fig.update_xaxes(showline=True, linewidth=2, linecolor='black', mirror=True, zeroline=True, zerolinewidth=1, zerolinecolor='grey', tickfont_size=20)
                fig=fig.update_yaxes(title='MWh', showgrid=True, gridwidth=1, zeroline=False, gridcolor='grey', showline=True, linewidth=2, linecolor='black', mirror=True, tickfont_size=20, title_font_size=24)
                fig.write_html(osp.join(result_directory, f'detailed_generation_{r.replace(r"|","-")}_{s}.html'))
                
                
    def plot_volumes(self, result_directory):
        if not osp.isdir(result_directory):
            os.makedirs(result_directory)
        if not hasattr(self, 'volumes'):
            self.read_volumes()
        for r in self.regions:
            for sh in self.volumes.columns.levels[2]:
                fig = px.line(self.volumes.loc[:,(r,slice(None),sh)].droplevel([0,2],axis=1))
                fig=fig.update_layout(style_graph(1200,2000), title=f'Volumes {r}', title_font_size=24, uniformtext_minsize=24, uniformtext_mode='hide', legend=dict(font=dict(size=22)))
                fig=fig.update_annotations(font_size=24)
                fig=fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[1]))
                fig=fig.update_xaxes(showline=True, linewidth=2, linecolor='black', mirror=True, zeroline=True, zerolinewidth=1, zerolinecolor='grey', tickfont_size=20)
                fig=fig.update_yaxes(title='MWh', showgrid=True, gridwidth=1, zeroline=False, gridcolor='grey', showline=True, linewidth=2, linecolor='black', mirror=True, tickfont_size=20, title_font_size=24)
                fig.write_html(osp.join(result_directory, f'volumes_{r.replace(r"|","-")}_{sh}.html'))
                    
    def plot_demand_marginal_costs_mon_region(self, result_directory):
        if not osp.isdir(result_directory):
            os.makedirs(result_directory)
        if not hasattr(self, 'marginal_costs'):
            self.read_marginal_costs()
        marginal_costs = self.marginal_costs['ActivePowerDemand']
        for r in self.regions:
            marginal_costs_mon = pd.concat({jdd.stochastic_scenarios[s] : marginal_costs[(r,s)].sort_values(ascending=False).reset_index(drop=True) for s in marginal_costs[r].columns},axis=1)
            marginal_costs_mon.index/=marginal_costs_mon.index[-1]
            fig = px.line(marginal_costs_mon)
            fig=fig.update_layout(style_graph(1200,2000), title=f'Marginal Costs for demand in {r}', title_font_size=24, uniformtext_minsize=24, uniformtext_mode='hide', legend=dict(font=dict(size=22)))
            fig=fig.update_annotations(font_size=24)
            fig=fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[1]))
            fig=fig.update_xaxes(tickformat='.1%', showline=True, linewidth=2, linecolor='black', mirror=True, zeroline=True, zerolinewidth=1, zerolinecolor='grey', tickfont_size=20)
            fig=fig.update_yaxes(title='MWh', showgrid=True, gridwidth=1, zeroline=False, gridcolor='grey', showline=True, linewidth=2, linecolor='black', mirror=True, tickfont_size=20, title_font_size=24)
            fig.write_html(osp.join(result_directory, f'marginal_costs_{r.replace(r"|","-")}.html'))
            
    def plot_demand_marginal_costs_mon_scenario(self, result_directory):
        if not osp.isdir(result_directory):
            os.makedirs(result_directory)
        if not hasattr(self, 'marginal_costs'):
            self.read_marginal_costs()
        marginal_costs = self.marginal_costs['ActivePowerDemand']
        for idx,s in enumerate(self.stochastic_scenarios):
            marginal_costs_mon = pd.concat({r : marginal_costs[(r,idx)].sort_values(ascending=False).reset_index(drop=True) for r in self.regions},axis=1)
            marginal_costs_mon.index/=marginal_costs_mon.index[-1]
            fig = px.line(marginal_costs_mon)
            fig=fig.update_layout(style_graph(1200,2000), title=f'Marginal Costs for scenario {s}', title_font_size=24, uniformtext_minsize=24, uniformtext_mode='hide', legend=dict(font=dict(size=22)))
            fig=fig.update_annotations(font_size=24)
            fig=fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[1]))
            fig=fig.update_xaxes(tickformat='.1%', showline=True, linewidth=2, linecolor='black', mirror=True, zeroline=True, zerolinewidth=1, zerolinecolor='grey', tickfont_size=20)
            fig=fig.update_yaxes(title='MWh', showgrid=True, gridwidth=1, zeroline=False, gridcolor='grey', showline=True, linewidth=2, linecolor='black', mirror=True, tickfont_size=20, title_font_size=24)
            fig.write_html(osp.join(result_directory, f'marginal_costs_{s}.html'))

def read_p4r_dir(rep, index_fct=lambda _:_):
    data = dict()
    for f in os.listdir(rep):
        if not f.endswith('.csv'):
            continue
        logger.info('Reading file '+f)
        k = index_fct(f)
        data[k] = pd.read_csv(osp.join(rep,f))
        data[k].set_index([c for c in data[k].columns if c !='values' and c != 'Value'],inplace=True)
        if not isinstance(data[k].index, pd.MultiIndex):
            data[k].index = pd.MultiIndex.from_tuples([tuple(_.split('|')) for _ in data[k].index])
            data[k].index.names = ['Category','Year','TS','Sector','Zone']
            data[(k, 'yearly')] = data[k].groupby(level=['Category','Year','Sector','Zone']).sum()
    return data


if __name__ == "__main__":
    data_dir = r"C:\Users\DELL\OpenMod4A\plan4res\outputs\Output_Stochastic\SN_ID_2030_v2"
    year = 2030

    jdd = JDDP4R(data_dir=data_dir, year=year)

    jdd.load_genesys_data(detailed_data=True)
    jdd.read_simul_output()

    jdd.compare_genmod_and_p4r_capacity(
        comparison_file=osp.join(data_dir, "capacity_stochastic.xlsx")
    )

    jdd.compare_genmod_and_p4r_generation(
        comparison_file=osp.join(data_dir, "generation_stochastic.xlsx")
    )

    print("Traitement terminé.")