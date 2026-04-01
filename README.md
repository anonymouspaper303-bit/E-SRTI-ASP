# E-SRTI-ASP (Anonymous Submission)

### Note
*This repository is provided for anonymous review purposes.
It contains supplementary material, implementation details, and running examples with snapshots to support the submitted paper.
All necessary ASP programs can be found under `rules` folder.*

---

## Overview
E-SRTI-ASP is a framework for generating explanations to user's queries about solutions to the stable roommates problems.

---

### Input Format
The input directory should contain the following files:
- `i.lp`   -- Personalized-SRTI instance \(I\)
- `M.lp`   -- stable matching \(M\)
- `h.csv`  -- habitual information (optional)

The system generates a query file (`generated_q.lp`) through interactive user input in the input directory.

----

### Running the System
To run the system:

 `python3.14 E-SRTI-ASP.py --input-dir <path_to_input_folder>`

The `--input-dir` argument is optional. If not provided, the system uses the default directory: `./matching`.

E-SRTI-ASP allows users to ask queries one after another and make suggestions for alternative matchings when appropriate. The interaction continues until the user chooses to exit.

---

### Running Examples
The `running examples` folder contains three different instances with their inputs. For each instance, the corresponding PDF files include interface snapshots illustrating the interactions.

One of these examples is presented in the submitted paper as a dialogue (Figure 1). The corresponding illsutration can be found in `figure1-interface.pdf`.

---

### Benchmark Instances
Benchmark instances are available in the `benchmark instances` folder.

#### Requirements
- Python 3.14

### Disclaimer
This repository is anonymized for the review process. All identifying information has been removed.
