import {
  Conversation,
  ConversationContent,
  Message,
  MessageContent,
  MessageAvatar,
  Response,
} from "nexus-ui";

// A full narrative exchange inside the auto-scrolling transcript container:
// player turn, storyteller prose, follow-up prompt. The Conversation wraps the
// scroll viewport; messages alternate user/assistant with avatars.
export const Transcript = () => (
  <div style={{ height: 460, width: 560, display: "flex", flexDirection: "column" }}>
    <Conversation>
      <ConversationContent>
        <Message from="user">
          <MessageContent>
            I keep my hand on the railing and look down into the flood district.
            How far does the water reach tonight?
          </MessageContent>
          <MessageAvatar src="" name="You" />
        </Message>
        <Message from="assistant">
          <MessageContent>
            <Response>
              {
                "The tide has climbed past the second-floor windows of the old customs house. Lantern-light from the **Tidewardens'** skiffs slides across the black surface, and somewhere below, a bell buoy tolls once, then falls silent."
              }
            </Response>
          </MessageContent>
          <MessageAvatar src="" name="Narrator" />
        </Message>
        <Message from="user">
          <MessageContent>
            I signal the nearest skiff and ask the wardens to take me across.
          </MessageContent>
          <MessageAvatar src="" name="You" />
        </Message>
      </ConversationContent>
    </Conversation>
  </div>
);

// A single assistant turn rendering streamed markdown prose — the most common
// shape the storyteller produces.
export const SingleTurn = () => (
  <div style={{ height: 300, width: 560, display: "flex", flexDirection: "column" }}>
    <Conversation>
      <ConversationContent>
        <Message from="assistant">
          <MessageContent>
            <Response>
              {
                "Cassius doesn't look up from the map. *\"The Prince already knows you're in the city,\"* he says. *\"The only question left is whether you walk into the Spire on your own feet, or are carried.\"*"
              }
            </Response>
          </MessageContent>
          <MessageAvatar src="" name="Narrator" />
        </Message>
      </ConversationContent>
    </Conversation>
  </div>
);
