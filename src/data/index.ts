import criteriaData from './criteria.json';

export interface Criterion {
    label: string;
    weight: number;
}

export interface Scenario {
    name: string;
    criteria: Criterion[];
}

export interface Sector {
    name: string;
    scenarios: Scenario[];
}

export interface CriteriaDatabase {
    sectors: Sector[];
}

export const AUDIT_CRITERIA_DB: CriteriaDatabase = criteriaData;

export const getCriteriaForScenario = (sectorName: string, scenarioName: string): string => {
    const sector = AUDIT_CRITERIA_DB.sectors.find(s => s.name === sectorName);
    if (!sector) return '';

    const scenario = sector.scenarios.find(s => s.name === scenarioName);
    if (!scenario) return '';

    return scenario.criteria.map(c => `- ${c.label} (Peso: ${c.weight})`).join('\n');
};
