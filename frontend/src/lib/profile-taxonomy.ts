/** Suggested values for guided profile inputs. Custom values are always allowed. */

export type TaxonomyOption = { value: string; label: string };

export const FIELDS_OF_STUDY: TaxonomyOption[] = [
  { value: "Computer Science", label: "Computer Science" },
  { value: "Software Engineering", label: "Software Engineering" },
  { value: "Data Science", label: "Data Science" },
  { value: "Information Systems", label: "Information Systems" },
  { value: "Finance", label: "Finance" },
  { value: "Business", label: "Business" },
  { value: "Economics", label: "Economics" },
  { value: "Mathematics", label: "Mathematics" },
  { value: "Electrical Engineering", label: "Electrical Engineering" },
  { value: "Mechanical Engineering", label: "Mechanical Engineering" },
];

export const DEGREE_TYPES: TaxonomyOption[] = [
  { value: "Associate", label: "Associate" },
  { value: "AA", label: "AA" },
  { value: "AS", label: "AS" },
  { value: "AST", label: "AST" },
  { value: "Bachelor's", label: "Bachelor's" },
  { value: "BA", label: "BA" },
  { value: "BS", label: "BS" },
  { value: "Master's", label: "Master's" },
  { value: "MS", label: "MS" },
  { value: "MBA", label: "MBA" },
  { value: "PhD", label: "PhD" },
  { value: "Certificate", label: "Certificate" },
];

export const TARGET_ROLES: TaxonomyOption[] = [
  { value: "Software Engineer", label: "Software Engineer" },
  { value: "Software Engineering Intern", label: "Software Engineering Intern" },
  { value: "Data Analyst", label: "Data Analyst" },
  { value: "Data Scientist", label: "Data Scientist" },
  { value: "Product Manager", label: "Product Manager" },
  { value: "Solutions Engineer", label: "Solutions Engineer" },
  { value: "Solutions Architect", label: "Solutions Architect" },
  { value: "Cybersecurity Analyst", label: "Cybersecurity Analyst" },
  { value: "Financial Analyst", label: "Financial Analyst" },
  { value: "Technical Consultant", label: "Technical Consultant" },
];

export const INDUSTRIES: TaxonomyOption[] = [
  { value: "Technology", label: "Technology" },
  { value: "Fintech", label: "Fintech" },
  { value: "Financial Services", label: "Financial Services" },
  { value: "Consulting", label: "Consulting" },
  { value: "Healthcare", label: "Healthcare" },
  { value: "Automotive", label: "Automotive" },
  { value: "Aerospace", label: "Aerospace" },
  { value: "Retail", label: "Retail" },
  { value: "Government", label: "Government" },
  { value: "Education", label: "Education" },
];

export const EXPERIENCE_LEVELS: TaxonomyOption[] = [
  { value: "Intern", label: "Intern" },
  { value: "New Grad", label: "New Grad" },
  { value: "Entry", label: "Entry" },
  { value: "Junior", label: "Junior" },
  { value: "Mid", label: "Mid" },
  { value: "Senior", label: "Senior" },
  { value: "Staff", label: "Staff" },
  { value: "Lead", label: "Lead" },
  { value: "Manager", label: "Manager" },
];

export const WORK_SETUPS: TaxonomyOption[] = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "Onsite" },
];

export const OPPORTUNITY_PREFERENCES: TaxonomyOption[] = [
  { value: "both", label: "Both" },
  { value: "internships", label: "Internships" },
  { value: "roles", label: "Roles" },
];

export const ACADEMIC_YEARS: TaxonomyOption[] = [
  { value: "freshman", label: "Freshman" },
  { value: "sophomore", label: "Sophomore" },
  { value: "junior", label: "Junior" },
  { value: "senior", label: "Senior" },
  { value: "final_year", label: "Final year" },
  { value: "graduate", label: "Graduate" },
];

export const SUGGESTED_LOCATIONS: TaxonomyOption[] = [
  { value: "San Francisco", label: "San Francisco" },
  { value: "Bay Area", label: "Bay Area" },
  { value: "San Jose", label: "San Jose" },
  { value: "New York", label: "New York" },
  { value: "Seattle", label: "Seattle" },
  { value: "Austin", label: "Austin" },
  { value: "Boston", label: "Boston" },
  { value: "Chicago", label: "Chicago" },
  { value: "Remote", label: "Remote" },
];

/** Short maintained suggestion list — not an exhaustive skill catalog. */
export const SUGGESTED_SKILLS: TaxonomyOption[] = [
  { value: "Python", label: "Python" },
  { value: "SQL", label: "SQL" },
  { value: "JavaScript", label: "JavaScript" },
  { value: "TypeScript", label: "TypeScript" },
  { value: "React", label: "React" },
  { value: "Java", label: "Java" },
  { value: "Excel", label: "Excel" },
];
