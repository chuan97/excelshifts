A shift scheduler for anesthesiology residents.

The input is an .xlsx containing a table that defines the residents, the days of the month, some preasigned shifts (G, T, R, M, U, UT, P), and some days were a given resident is unavailable (V, E). The library is designed to ingest the .xlsx with the table and a .yaml policy specifying some rules that the shifts must follow. It then fills the rest of the table by assigning more anesthesiology shifts (G, T, R, M) while enforcing the rules specified in the policy file.

The shifts are asigned by solving the constraint programming problem defined by the rules in the policy file. The library uses Google's OR-tools as a backend. A `CpModel` is initialized, and each (resident, day, shift type) tuple is assigned a binary variable indicating whether that resident does that shift type that day. Each rule in the policy file is used to initialize a constraint in the model. The constraints are reified with an auxiliary enable variable that can be used to dynamically toggle them on and off. The solver first attemps to solve the model with all constraints enabled. If the solver finds the model unsatisfiable, the constraints are disabled iteratively until the model becomes satisfiable. Then, the solver attemps to reenable them iteratively, to ensure that only the minimum subset of unsatisfiable constraints end up disabled. The resulting model is solved and the non-zero (resident, day, shift type) tuples are printed back to the .xlsx file.

Example input:
![alt text](https://github.com/chuan97/excelshifts/blob/main/images/input.png "Input")

Example output:
![alt text](https://github.com/chuan97/excelshifts/blob/main/images/output.png "Output")
