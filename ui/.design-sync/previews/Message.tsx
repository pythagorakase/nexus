import {
  Message,
  MessageContent,
  MessageAvatar,
  Response,
} from "nexus-ui";

// Both roles side by side: the user bubble (right-aligned, primary fill) and the
// assistant bubble (left-aligned, secondary fill). This is the core chat unit.
export const Roles = () => (
  <div style={{ width: 560 }}>
    <Message from="user">
      <MessageContent>
        I draw my coat tighter and step off the skiff onto the customs-house steps.
      </MessageContent>
      <MessageAvatar src="" name="You" />
    </Message>
    <Message from="assistant">
      <MessageContent>
        The wood is slick with brine. Above you, a single window glows amber, and
        a silhouette watches you climb.
      </MessageContent>
      <MessageAvatar src="" name="Narrator" />
    </Message>
  </div>
);

// Assistant turn whose content is rich markdown via Response — emphasis,
// dialogue, and a short list of what the scene offers.
export const RichResponse = () => (
  <div style={{ width: 560 }}>
    <Message from="assistant">
      <MessageContent>
        <Response>
          {[
            "The Archivist sets down her pen. *\"You've come a long way to ask a dead woman for directions.\"*",
            "",
            "Three doors lead out of the reading room:",
            "",
            "- The **iron stair** down to the stacks",
            "- A **curtained arch** humming with cold air",
            "- The **clerk's office**, its lamp still lit",
          ].join("\n")}
        </Response>
      </MessageContent>
      <MessageAvatar src="" name="Narrator" />
    </Message>
  </div>
);

// A user message paired with a fallback avatar (no image src resolves, so the
// initials chip shows) — confirms the avatar ring + fallback styling.
export const PlayerTurn = () => (
  <div style={{ width: 560 }}>
    <Message from="user">
      <MessageContent>
        Ask her plainly: who sealed the lower archive, and why?
      </MessageContent>
      <MessageAvatar src="" name="Mira" />
    </Message>
  </div>
);
