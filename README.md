The script takes in an excel file with a table of the residents and days of the month. 
The table includes some preasigned shifts (G, T, R, M, U, UT) and some days were a given resident is unavailable (V, E).
The script fills the rest of the table by assigning more shifts (G, T, R, M) while enforcing some hardcoded constraints that reflect the policy of the hospital.
An example of a constraint would be that if a resident does a shift one day, he cannot do a shift the following day.
This is implemented as a constrained minimization problem using Google's OR-tools.
The optimization goal is to minimize the number of days in which a particular shift is not covered by any resident.
The script outputs a copy of the input excel file with the newly assigned shifts.

Example input:
![alt text]([https://github.com/chuan97/excelshifts/blob/main/input.png] "Input")

Example output:
