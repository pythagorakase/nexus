import express, { type Express } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import { createProxyMiddleware } from "http-proxy-middleware";
import multer from "multer";
import fs from "fs/promises";
import path from "path";

// WebSocket proxy instance for /ws/narrative. http-proxy-middleware only
// attaches its upgrade listener lazily (after the first plain HTTP request
// through the same middleware), which never happens on a WS-only path - so
// the HTTP server must wire `upgrade` events to this instance explicitly
// (see server/index.ts).
let narrativeWsProxy: ReturnType<typeof createProxyMiddleware> | null = null;

export function getNarrativeWsProxy() {
  return narrativeWsProxy;
}

// Register proxy BEFORE body parsing middleware
export function registerProxyRoutes(app: Express): void {
  const narrativePort = process.env.NARRATIVE_API_PORT || "8002";
  const narrativeTarget = process.env.NARRATIVE_API_URL || `http://localhost:${narrativePort}`;

  // Proxy for Narrative API (FastAPI backend on port 8002)
  // Handles generation + incubator management without intercepting local narrative read routes
  const narrativeProxyOptions = {
    target: narrativeTarget,
    changeOrigin: true,
  };

  app.use("/api/narrative/continue", createProxyMiddleware({
    ...narrativeProxyOptions,
    pathRewrite: (path) => `/api/narrative/continue${path}`,
  }));
  app.use("/api/narrative/status", createProxyMiddleware({
    ...narrativeProxyOptions,
    pathRewrite: (path) => `/api/narrative/status${path}`,
  }));
  app.use("/api/narrative/incubator", createProxyMiddleware({
    ...narrativeProxyOptions,
    pathRewrite: (path) => `/api/narrative/incubator${path}`,
  }));
  app.use("/api/narrative/approve", createProxyMiddleware({
    ...narrativeProxyOptions,
    pathRewrite: (path) => `/api/narrative/approve${path}`,
  }));
  app.use("/api/narrative/select-choice", createProxyMiddleware({
    ...narrativeProxyOptions,
    pathRewrite: (path) => `/api/narrative/select-choice${path}`,
  }));

  // Proxy for Story Wizard endpoints
  app.use("/api/story", createProxyMiddleware({
    ...narrativeProxyOptions,
    pathRewrite: (path) => `/api/story${path}`,
  }));

  // Proxy for Slot endpoints (slot state, undo, model, lock)
  app.use("/api/slot", createProxyMiddleware({
    ...narrativeProxyOptions,
    pathRewrite: (path) => `/api/slot${path}`,
  }));

  // Proxy for Chunk Workflow endpoints
  app.use("/api/chunks", createProxyMiddleware({
    ...narrativeProxyOptions,
    pathRewrite: (path) => `/api/chunks${path}`,
  }));

  // Proxy for user-character endpoint (fetches protagonist name from global_variables)
  app.use("/api/user-character", createProxyMiddleware({
    ...narrativeProxyOptions,
    pathRewrite: (path) => `/api/user-character${path}`,
  }));

  // Proxy for config endpoint (serves model configuration from nexus.toml)
  app.use("/api/config", createProxyMiddleware({
    ...narrativeProxyOptions,
    pathRewrite: (path) => `/api/config${path}`,
  }));

  // Settings GET/PATCH live on the FastAPI service (typed, Pydantic-validated,
  // formatting-preserving writes through nexus.config.loader.save_settings).
  // All /api/settings paths proxy through; there are no Express-local settings
  // routes (the PWA icon upload was retired — icons are per-theme and locked).
  app.use("/api/settings", createProxyMiddleware({
    ...narrativeProxyOptions,
    pathRewrite: (path) => (path === "/" ? "/api/settings" : `/api/settings${path}`),
  }));

  narrativeWsProxy = createProxyMiddleware({ ...narrativeProxyOptions, ws: true });
  app.use("/ws/narrative", narrativeWsProxy);
}

export async function registerRoutes(app: Express): Promise<Server> {

  app.get("/status", (_req, res) => {
    res.json({ status: "ok" });
  });

  // Narrative routes

  // GET /api/narrative/seasons - Get all seasons
  app.get("/api/narrative/seasons", async (req, res) => {
    try {
      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      const seasons = await storage.getAllSeasons(slot);
      res.json(seasons);
    } catch (error) {
      console.error("Error fetching seasons:", error);
      res.status(500).json({ error: "Failed to fetch seasons" });
    }
  });

  // GET /api/narrative/episodes/:seasonId - Get episodes by season
  app.get("/api/narrative/episodes/:seasonId", async (req, res) => {
    try {
      const seasonId = parseInt(req.params.seasonId);
      if (isNaN(seasonId)) {
        return res.status(400).json({ error: "Invalid season ID" });
      }

      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      const episodes = await storage.getEpisodesBySeason(seasonId, slot);
      res.json(episodes);
    } catch (error) {
      console.error("Error fetching episodes:", error);
      res.status(500).json({ error: "Failed to fetch episodes" });
    }
  });

  // GET /api/narrative/latest-chunk - Get the newest chunk
  app.get("/api/narrative/latest-chunk", async (req, res) => {
    try {
      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      const chunk = await storage.getLatestChunk(slot);
      if (!chunk) {
        return res.status(404).json({ error: "No chunks found" });
      }
      res.json(chunk);
    } catch (error) {
      console.error("Error fetching latest chunk:", error);
      res.status(500).json({ error: "Failed to fetch latest chunk" });
    }
  });

  // GET /api/narrative/outline - Story outline (season/episode/scene/slug per
  // committed chunk, story order). Read-only; powers the right-rail story tree.
  app.get("/api/narrative/outline", async (req, res) => {
    try {
      const slot = req.query.slot
        ? parseInt(req.query.slot as string, 10)
        : undefined;
      if (slot !== undefined && Number.isNaN(slot)) {
        return res.status(400).json({ error: "slot must be an integer" });
      }
      const outline = await storage.getChunkOutline(slot);
      res.json(outline);
    } catch (error) {
      console.error("Error fetching outline:", error);
      res.status(500).json({ error: "Failed to fetch outline" });
    }
  });

  // GET /api/narrative/chunks/:chunkId - Get a single committed chunk by id.
  // Read-only; powers historical (non-frontier) reading in the reader.
  app.get("/api/narrative/chunks/:chunkId", async (req, res) => {
    try {
      const chunkId = parseInt(req.params.chunkId);
      if (isNaN(chunkId)) {
        return res.status(400).json({ error: "Invalid chunk ID" });
      }

      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      const chunk = await storage.getChunkById(chunkId, slot);
      if (!chunk) {
        return res.status(404).json({ error: `Chunk ${chunkId} not found` });
      }
      res.json(chunk);
    } catch (error) {
      console.error("Error fetching chunk:", error);
      res.status(500).json({ error: "Failed to fetch chunk" });
    }
  });

  // GET /api/narrative/chunks/:chunkId/adjacent - Get previous and next chunks
  app.get("/api/narrative/chunks/:chunkId/adjacent", async (req, res) => {
    try {
      const chunkId = parseInt(req.params.chunkId);
      if (isNaN(chunkId)) {
        return res.status(400).json({ error: "Invalid chunk ID" });
      }

      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      const result = await storage.getAdjacentChunks(chunkId, slot);
      res.json(result);
    } catch (error) {
      console.error("Error fetching adjacent chunks:", error);
      res.status(500).json({ error: "Failed to fetch adjacent chunks" });
    }
  });

  // GET /api/narrative/chunks/:chunkId/context - Get character/place references for a chunk
  // (must register before the :seasonId/:episodeId route, which would otherwise shadow it)
  app.get("/api/narrative/chunks/:chunkId/context", async (req, res) => {
    try {
      const chunkId = parseInt(req.params.chunkId);
      if (isNaN(chunkId)) {
        return res.status(400).json({ error: "Invalid chunk ID" });
      }

      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      const context = await storage.getChunkContext(chunkId, slot);
      res.json(context);
    } catch (error) {
      console.error("Error fetching chunk context:", error);
      res.status(500).json({ error: "Failed to fetch chunk context" });
    }
  });

  // GET /api/narrative/chunks/:seasonId/:episodeId - Get chunks by season and episode with pagination
  app.get("/api/narrative/chunks/:seasonId/:episodeId", async (req, res) => {
    try {
      const seasonId = parseInt(req.params.seasonId);
      const episodeId = parseInt(req.params.episodeId);
      if (isNaN(seasonId) || isNaN(episodeId)) {
        return res.status(400).json({ error: "Invalid season or episode ID" });
      }

      const offset = parseInt(req.query.offset as string) || 0;
      const limit = parseInt(req.query.limit as string) || 50;
      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;

      const result = await storage.getChunksBySeasonAndEpisode(seasonId, episodeId, offset, limit, slot);
      res.json(result);
    } catch (error) {
      console.error("Error fetching chunks:", error);
      res.status(500).json({ error: "Failed to fetch chunks" });
    }
  });

  // Character routes

  // GET /api/characters - Get all characters with optional ID range filter
  app.get("/api/characters", async (req, res) => {
    try {
      const startId = req.query.startId ? parseInt(req.query.startId as string) : undefined;
      const endId = req.query.endId ? parseInt(req.query.endId as string) : undefined;
      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;

      const characters = await storage.getCharacters(startId, endId, slot);
      res.json(characters);
    } catch (error) {
      console.error("Error fetching characters:", error);
      res.status(500).json({ error: "Failed to fetch characters" });
    }
  });

  // GET /api/characters/:id/relationships - Get character relationships
  app.get("/api/characters/:id/relationships", async (req, res) => {
    try {
      const characterId = parseInt(req.params.id);
      if (isNaN(characterId)) {
        return res.status(400).json({ error: "Invalid character ID" });
      }

      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      const relationships = await storage.getCharacterRelationships(characterId, slot);
      res.json(relationships);
    } catch (error) {
      console.error("Error fetching character relationships:", error);
      res.status(500).json({ error: "Failed to fetch character relationships" });
    }
  });

  // GET /api/characters/:id/psychology - Get character psychology
  app.get("/api/characters/:id/psychology", async (req, res) => {
    try {
      const characterId = parseInt(req.params.id);
      if (isNaN(characterId)) {
        return res.status(400).json({ error: "Invalid character ID" });
      }

      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      const psychology = await storage.getCharacterPsychology(characterId, slot);
      if (!psychology) {
        return res.status(404).json({ error: "Character psychology not found" });
      }
      res.json(psychology);
    } catch (error) {
      console.error("Error fetching character psychology:", error);
      res.status(500).json({ error: "Failed to fetch character psychology" });
    }
  });

  // Place and Zone routes

  // GET /api/places - Get all places
  app.get("/api/places", async (req, res) => {
    try {
      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      const places = await storage.getAllPlaces(slot);
      res.json(places);
    } catch (error) {
      console.error("Error fetching places:", error);
      res.status(500).json({ error: "Failed to fetch places" });
    }
  });

  // GET /api/current-place - The narrative's current location (read-only):
  // the 'setting' place reference on the latest committed chunk. 404 when
  // the story has no setting references yet.
  app.get("/api/current-place", async (req, res) => {
    try {
      const slot = req.query.slot
        ? parseInt(req.query.slot as string, 10)
        : undefined;
      // Reject malformed slots loudly — a NaN would silently fall back to
      // the default database and serve the wrong slot's location.
      if (slot !== undefined && Number.isNaN(slot)) {
        return res.status(400).json({ error: "slot must be an integer" });
      }
      const currentPlace = await storage.getCurrentPlace(slot);
      if (!currentPlace) {
        return res.status(404).json({ error: "No current place recorded" });
      }
      res.json(currentPlace);
    } catch (error) {
      console.error("Error fetching current place:", error);
      res.status(500).json({ error: "Failed to fetch current place" });
    }
  });

  // GET /api/zones - Get all zones
  app.get("/api/zones", async (req, res) => {
    try {
      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      const zones = await storage.getAllZones(slot);
      res.json(zones);
    } catch (error) {
      console.error("Error fetching zones:", error);
      res.status(500).json({ error: "Failed to fetch zones" });
    }
  });

  // Additional faction route (for completeness)
  app.get("/api/factions", async (req, res) => {
    try {
      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      const factions = await storage.getAllFactions(slot);
      res.json(factions);
    } catch (error) {
      console.error("Error fetching factions:", error);
      res.status(500).json({ error: "Failed to fetch factions" });
    }
  });

  // Settings GET/PATCH are proxied to the FastAPI service (registerProxyRoutes).

  // Multer configuration for file uploads
  const upload = multer({
    dest: "/tmp/",
    limits: {
      fileSize: 15 * 1024 * 1024, // 15MB max file size
    },
    fileFilter: (req, file, cb) => {
      // Accept only PNG, JPEG, and JPG
      const allowedMimeTypes = ['image/png', 'image/jpeg', 'image/jpg'];
      const allowedExtensions = ['.png', '.jpg', '.jpeg'];

      const ext = path.extname(file.originalname).toLowerCase();
      const mimeType = file.mimetype.toLowerCase();

      if (allowedMimeTypes.includes(mimeType) && allowedExtensions.includes(ext)) {
        cb(null, true);
      } else {
        cb(new Error(`Invalid file type. Only PNG and JPEG images are allowed. Got: ${file.mimetype}`));
      }
    },
  });

  // Serve uploaded portraits straight from the runtime upload directory.
  // Vite only mirrors client/public in dev; a production bundle serves the
  // frozen dist copy, which predates any runtime upload. This route makes
  // portrait files resolvable in both modes.
  app.use(
    "/character_portraits",
    express.static(path.join(import.meta.dirname, "..", "client", "public", "character_portraits")),
  );

  // Character image routes
  app.get("/api/characters/:id/images", async (req, res) => {
    try {
      const characterId = parseInt(req.params.id);
      if (isNaN(characterId)) {
        return res.status(400).json({ error: "Invalid character ID" });
      }

      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      const images = await storage.getCharacterImages(characterId, slot);
      res.json(images);
    } catch (error) {
      console.error("Error fetching character images:", error);
      res.status(500).json({ error: "Failed to fetch character images" });
    }
  });

  app.post("/api/characters/:id/images", upload.array("images", 10), async (req, res) => {
    try {
      const characterId = parseInt(req.params.id);
      if (isNaN(characterId)) {
        return res.status(400).json({ error: "Invalid character ID" });
      }

      if (!req.files || !Array.isArray(req.files) || req.files.length === 0) {
        return res.status(400).json({ error: "No files uploaded" });
      }

      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;

      const characterDir = path.join(import.meta.dirname, "..", "client", "public", "character_portraits", String(characterId));
      await fs.mkdir(characterDir, { recursive: true });

      // Get current max display order (in the same slot the rows are written
      // to — omitting the slot here used to consult the default database and
      // mis-flag a slot's first portrait as non-main).
      const existingImages = await storage.getCharacterImages(characterId, slot);
      let maxOrder = existingImages.reduce((max, img) => Math.max(max, img.displayOrder), -1);

      const uploadedImages = [];
      for (const file of req.files) {
        // Sanitize filename: only allow alphanumeric, dash, underscore, and extension
        const ext = path.extname(file.originalname).toLowerCase();
        const sanitized = file.originalname
          .replace(ext, '')
          .replace(/[^a-zA-Z0-9_-]/g, '_')
          .substring(0, 50); // Limit base name length
        const filename = `${Date.now()}_${sanitized}${ext}`;
        const destPath = path.join(characterDir, filename);
        await fs.copyFile(file.path, destPath);
        await fs.unlink(file.path);

        const relativePath = `character_portraits/${characterId}/${filename}`;

        const isMain = existingImages.length === 0 && uploadedImages.length === 0 ? 1 : 0;
        maxOrder++;

        let image;
        try {
          image = await storage.addCharacterImage(characterId, relativePath, isMain, maxOrder, slot);
        } catch (insertError) {
          // Don't leave an orphaned file behind when the row insert fails;
          // the error still propagates to the client.
          await fs.unlink(destPath).catch(() => {});
          throw insertError;
        }
        uploadedImages.push(image);
      }

      res.json({ success: true, images: uploadedImages });
    } catch (error: any) {
      console.error("Error uploading character images:", error);
      // Handle multer-specific errors
      if (error.code === 'LIMIT_FILE_SIZE') {
        return res.status(413).json({ error: "File too large. Maximum size is 15MB." });
      }
      if (error.message && error.message.includes('Invalid file type')) {
        return res.status(400).json({ error: error.message });
      }
      res.status(500).json({ error: "Failed to upload images" });
    }
  });

  app.put("/api/characters/:id/images/:imageId/main", async (req, res) => {
    try {
      const characterId = parseInt(req.params.id);
      const imageId = parseInt(req.params.imageId);
      if (isNaN(characterId) || isNaN(imageId)) {
        return res.status(400).json({ error: "Invalid IDs" });
      }

      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      await storage.setMainCharacterImage(characterId, imageId, slot);
      res.json({ success: true });
    } catch (error) {
      console.error("Error setting main character image:", error);
      res.status(500).json({ error: "Failed to set main image" });
    }
  });

  app.delete("/api/characters/:id/images/:imageId", async (req, res) => {
    try {
      const characterId = parseInt(req.params.id);
      const imageId = parseInt(req.params.imageId);
      if (isNaN(characterId) || isNaN(imageId)) {
        return res.status(400).json({ error: "Invalid IDs" });
      }

      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;

      // Get image info to delete file (from the same slot the row lives in)
      const images = await storage.getCharacterImages(characterId, slot);
      const image = images.find(img => img.id === imageId);

      if (image) {
        const filePath = path.join(import.meta.dirname, "..", "client", "public", image.filePath);
        try {
          await fs.unlink(filePath);
        } catch (err) {
          console.warn("Could not delete image file:", filePath, err);
        }
      }

      await storage.deleteCharacterImage(imageId, slot);
      res.json({ success: true });
    } catch (error) {
      console.error("Error deleting character image:", error);
      res.status(500).json({ error: "Failed to delete image" });
    }
  });

  // Place image routes
  app.get("/api/places/:id/images", async (req, res) => {
    try {
      const placeId = parseInt(req.params.id);
      if (isNaN(placeId)) {
        return res.status(400).json({ error: "Invalid place ID" });
      }

      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      const images = await storage.getPlaceImages(placeId, slot);
      res.json(images);
    } catch (error) {
      console.error("Error fetching place images:", error);
      res.status(500).json({ error: "Failed to fetch place images" });
    }
  });

  app.post("/api/places/:id/images", upload.array("images", 10), async (req, res) => {
    try {
      const placeId = parseInt(req.params.id);
      if (isNaN(placeId)) {
        return res.status(400).json({ error: "Invalid place ID" });
      }

      if (!req.files || !Array.isArray(req.files) || req.files.length === 0) {
        return res.status(400).json({ error: "No files uploaded" });
      }

      const placeDir = path.join(import.meta.dirname, "..", "client", "public", "place_images", String(placeId));
      await fs.mkdir(placeDir, { recursive: true });

      // Get current max display order
      const existingImages = await storage.getPlaceImages(placeId);
      let maxOrder = existingImages.reduce((max, img) => Math.max(max, img.displayOrder), -1);

      const uploadedImages = [];
      for (const file of req.files) {
        // Sanitize filename: only allow alphanumeric, dash, underscore, and extension
        const ext = path.extname(file.originalname).toLowerCase();
        const sanitized = file.originalname
          .replace(ext, '')
          .replace(/[^a-zA-Z0-9_-]/g, '_')
          .substring(0, 50); // Limit base name length
        const filename = `${Date.now()}_${sanitized}${ext}`;
        const destPath = path.join(placeDir, filename);
        await fs.copyFile(file.path, destPath);
        await fs.unlink(file.path);

        const relativePath = `place_images/${placeId}/${filename}`;

        const isMain = existingImages.length === 0 && uploadedImages.length === 0 ? 1 : 0;
        maxOrder++;

        const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
        const image = await storage.addPlaceImage(placeId, relativePath, isMain, maxOrder, slot);
        uploadedImages.push(image);
      }

      res.json({ success: true, images: uploadedImages });
    } catch (error: any) {
      console.error("Error uploading place images:", error);
      // Handle multer-specific errors
      if (error.code === 'LIMIT_FILE_SIZE') {
        return res.status(413).json({ error: "File too large. Maximum size is 15MB." });
      }
      if (error.message && error.message.includes('Invalid file type')) {
        return res.status(400).json({ error: error.message });
      }
      res.status(500).json({ error: "Failed to upload images" });
    }
  });

  app.put("/api/places/:id/images/:imageId/main", async (req, res) => {
    try {
      const placeId = parseInt(req.params.id);
      const imageId = parseInt(req.params.imageId);
      if (isNaN(placeId) || isNaN(imageId)) {
        return res.status(400).json({ error: "Invalid IDs" });
      }

      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      await storage.setMainPlaceImage(placeId, imageId, slot);
      res.json({ success: true });
    } catch (error) {
      console.error("Error setting main place image:", error);
      res.status(500).json({ error: "Failed to set main image" });
    }
  });

  app.delete("/api/places/:id/images/:imageId", async (req, res) => {
    try {
      const placeId = parseInt(req.params.id);
      const imageId = parseInt(req.params.imageId);
      if (isNaN(placeId) || isNaN(imageId)) {
        return res.status(400).json({ error: "Invalid IDs" });
      }

      // Get image info to delete file
      const images = await storage.getPlaceImages(placeId);
      const image = images.find(img => img.id === imageId);

      if (image) {
        const filePath = path.join(import.meta.dirname, "..", "client", "public", image.filePath);
        try {
          await fs.unlink(filePath);
        } catch (err) {
          console.warn("Could not delete image file:", filePath, err);
        }
      }

      const slot = req.query.slot ? parseInt(req.query.slot as string) : undefined;
      await storage.deletePlaceImage(imageId, slot);
      res.json({ success: true });
    } catch (error) {
      console.error("Error deleting place image:", error);
      res.status(500).json({ error: "Failed to delete image" });
    }
  });

  const httpServer = createServer(app);

  return httpServer;
}
