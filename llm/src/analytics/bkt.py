"""Bayesian Knowledge Tracing (BKT).

Classical algorithm from Corbett & Anderson (1994).
Models the probability that a student has mastered a knowledge component
using four parameters per topic:

  P(L0) — prior probability of already knowing the topic
  P(T)  — probability of transitioning from not-knowing to knowing per attempt
  P(G)  — probability of guessing correctly without knowledge
  P(S)  — probability of slipping (wrong answer despite knowing)

After each observed response the algorithm updates P(know) via Bayes' theorem,
then applies the learning transit probability.

Literature defaults used here are taken from:
  Corbett & Anderson (1994), "Knowledge tracing: Modeling the acquisition
  of procedural knowledge", User Modeling and User-Adapted Interaction.
"""

# Default BKT parameters (well-established starting values from literature)
DEFAULT_P_KNOW: float = 0.10   # P(L0)
DEFAULT_P_TRANSIT: float = 0.10  # P(T)
DEFAULT_P_GUESS: float = 0.25  # P(G)
DEFAULT_P_SLIP: float = 0.10   # P(S)

# Mastery threshold: student is considered to have mastered a topic
# when P(know) >= this value (standard in ITS literature)
MASTERY_THRESHOLD: float = 0.95


def update(
    p_know: float,
    correct: bool,
    p_transit: float = DEFAULT_P_TRANSIT,
    p_guess: float = DEFAULT_P_GUESS,
    p_slip: float = DEFAULT_P_SLIP,
) -> float:
    """Update P(know) after observing one student response.

    Steps:
      1. Bayes update: incorporate the observed response.
      2. Learning transit: account for the possibility of learning.

    Parameters
    ----------
    p_know : float
        Current probability that the student knows the topic (0.0–1.0).
    correct : bool
        Whether the student answered correctly.
    p_transit : float
        Probability of learning per opportunity P(T).
    p_guess : float
        Probability of a correct guess without knowledge P(G).
    p_slip : float
        Probability of an error despite knowledge P(S).

    Returns
    -------
    float
        Updated P(know) in [0.0, 1.0], rounded to 4 decimal places.
    """
    # Step 1 — Bayes update
    if correct:
        p_obs_given_know = 1.0 - p_slip        # P(correct | know)
        p_obs_given_not_know = p_guess         # P(correct | not know)
    else:
        p_obs_given_know = p_slip              # P(wrong | know)
        p_obs_given_not_know = 1.0 - p_guess  # P(wrong | not know)

    p_obs = p_know * p_obs_given_know + (1.0 - p_know) * p_obs_given_not_know

    # Guard against division by zero (should not occur with valid params)
    if p_obs < 1e-10:
        p_know_given_obs = p_know
    else:
        p_know_given_obs = (p_know * p_obs_given_know) / p_obs

    # Step 2 — Learning transit
    p_know_new = p_know_given_obs + (1.0 - p_know_given_obs) * p_transit

    return round(min(1.0, max(0.0, p_know_new)), 4)


def predict_correct(
    p_know: float,
    p_guess: float = DEFAULT_P_GUESS,
    p_slip: float = DEFAULT_P_SLIP,
) -> float:
    """Predict the probability of a correct answer on the next attempt.

    P(correct) = P(know) * (1 - P(S)) + (1 - P(know)) * P(G)

    Parameters
    ----------
    p_know : float
        Current P(know) for the topic.
    p_guess : float
        P(G) parameter.
    p_slip : float
        P(S) parameter.

    Returns
    -------
    float
        Predicted probability in [0.0, 1.0], rounded to 4 decimal places.
    """
    p_correct = p_know * (1.0 - p_slip) + (1.0 - p_know) * p_guess
    return round(min(1.0, max(0.0, p_correct)), 4)


def is_mastered(p_know: float) -> bool:
    """Return True if P(know) has crossed the mastery threshold (0.95).

    Parameters
    ----------
    p_know : float
        Current P(know) for the topic.

    Returns
    -------
    bool
    """
    return p_know >= MASTERY_THRESHOLD
