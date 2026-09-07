export type ClaimState = "unowned" | "mine" | "taken";

/**
 * What the connect page offers for a verified group, given the doc's
 * owner_uid and the signed-in user. Firestore rules enforce the same
 * decision server-side; this mirrors it for the UI.
 */
export function claimState(
  ownerUid: string | null | undefined,
  userUid: string,
): ClaimState {
  if (ownerUid === null || ownerUid === undefined || ownerUid === "") {
    return "unowned";
  }
  return ownerUid === userUid ? "mine" : "taken";
}

export function claimDeniedMessage(state: ClaimState): string | null {
  if (state === "unowned") return null;
  if (state === "mine") return null;
  return "This group is already claimed by another account. Sign in with the account that claimed it, or ask the owner to transfer it.";
}
