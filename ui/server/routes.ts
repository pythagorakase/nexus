import type { Express } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import { createProxyMiddleware } from "http-proxy-middleware";
import multer from "multer";
import { exec } from "child_process";
import { promisify } from "util";
import fs from "fs/promises";
import path from "path";

const execAsync = promisify(exec);

// Register proxy BEFORE body parsing middleware
export function registerProxyRoutes(app: Express): void {
  // Proxy for Audition API (FastAPI backend)
  // Express strips /api/audition before passing to middleware, so we need to add it back
  // IMPORTANT: Must be registered BEFORE express.json() to access raw body stream
  const auditionProxy = createProxyMiddleware({
    target: "http://localhost:8000",
    changeOrigin: true,
    pathRewrite: (path) => `/api/audition${path}`,
  });

  app.use("/api/audition", auditionProxy);
}

export async function registerRoutes(app: Express): Promise<Server> {

  // Narrative routes
  
  // GET /api/narrative/seasons - Get all seasons
  app.get("/api/narrative/seasons", async (req, res) => {
    try {
      const seasons = await storage.getAllSeasons();
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
      
      const episodes = await storage.getEpisodesBySeason(seasonId);
      res.json(episodes);
    } catch (error) {
      console.error("Error fetching episodes:", error);
      res.status(500).json({ error: "Failed to fetch episodes" });
    }
  });

  // GET /api/narrative/chunks/:episodeId - Get chunks by episode with pagination
  app.get("/api/narrative/chunks/:episodeId", async (req, res) => {
    try {
      const episodeId = parseInt(req.params.episodeId);
      if (isNaN(episodeId)) {
        return res.status(400).json({ error: "Invalid episode ID" });
      }
      
      const offset = parseInt(req.query.offset as string) || 0;
      const limit = parseInt(req.query.limit as string) || 50;
      
      const result = await storage.getChunksByEpisode(episodeId, offset, limit);
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
      
      const characters = await storage.getCharacters(startId, endId);
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
      
      const relationships = await storage.getCharacterRelationships(characterId);
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
      
      const psychology = await storage.getCharacterPsychology(characterId);
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
      const places = await storage.getAllPlaces();
      res.json(places);
    } catch (error) {
      console.error("Error fetching places:", error);
      res.status(500).json({ error: "Failed to fetch places" });
    }
  });

  // GET /api/zones - Get all zones
  app.get("/api/zones", async (req, res) => {
    try {
      const zones = await storage.getAllZones();
      res.json(zones);
    } catch (error) {
      console.error("Error fetching zones:", error);
      res.status(500).json({ error: "Failed to fetch zones" });
    }
  });

  // Additional faction route (for completeness)
  app.get("/api/factions", async (req, res) => {
    try {
      const factions = await storage.getAllFactions();
      res.json(factions);
    } catch (error) {
      console.error("Error fetching factions:", error);
      res.status(500).json({ error: "Failed to fetch factions" });
    }
  });

  // Settings route
  app.get("/api/settings", async (req, res) => {
    try {
      const fs = await import("fs/promises");
      const path = await import("path");
      const settingsPath = path.join(process.cwd(), "..", "settings.json");
      const settingsData = await fs.readFile(settingsPath, "utf-8");
      const settings = JSON.parse(settingsData);
      res.json(settings);
    } catch (error) {
      console.error("Error fetching settings:", error);
      res.status(500).json({ error: "Failed to fetch settings" });
    }
  });

  // Multer configuration for file uploads
  const upload = multer({ dest: "/tmp/" });

  // Character image routes
  app.get("/api/characters/:id/images", async (req, res) => {
    try {
      const characterId = parseInt(req.params.id);
      if (isNaN(characterId)) {
        return res.status(400).json({ error: "Invalid character ID" });
      }

      const images = await storage.getCharacterImages(characterId);
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

      const characterDir = path.join(import.meta.dirname, "..", "client", "public", "character_portraits", String(characterId));
      await fs.mkdir(characterDir, { recursive: true });

      // Get current max display order
      const existingImages = await storage.getCharacterImages(characterId);
      let maxOrder = existingImages.reduce((max, img) => Math.max(max, img.displayOrder), -1);

      const uploadedImages = [];
      for (const file of req.files) {
        const ext = path.extname(file.originalname);
        const filename = `${Date.now()}_${Math.random().toString(36).substring(7)}${ext}`;
        const destPath = path.join(characterDir, filename);
        await fs.copyFile(file.path, destPath);
        await fs.unlink(file.path);

        const relativePath = `/character_portraits/${characterId}/${filename}`;
        const isMain = existingImages.length === 0 && uploadedImages.length === 0 ? 1 : 0;
        maxOrder++;

        const image = await storage.addCharacterImage(characterId, relativePath, isMain, maxOrder);
        uploadedImages.push(image);
      }

      res.json({ success: true, images: uploadedImages });
    } catch (error) {
      console.error("Error uploading character images:", error);
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

      await storage.setMainCharacterImage(characterId, imageId);
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

      // Get image info to delete file
      const images = await storage.getCharacterImages(characterId);
      const image = images.find(img => img.id === imageId);

      if (image) {
        const filePath = path.join(import.meta.dirname, "..", "client", "public", image.filePath);
        try {
          await fs.unlink(filePath);
        } catch (err) {
          console.warn("Could not delete image file:", filePath, err);
        }
      }

      await storage.deleteCharacterImage(imageId);
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

      const images = await storage.getPlaceImages(placeId);
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
        const ext = path.extname(file.originalname);
        const filename = `${Date.now()}_${Math.random().toString(36).substring(7)}${ext}`;
        const destPath = path.join(placeDir, filename);
        await fs.copyFile(file.path, destPath);
        await fs.unlink(file.path);

        const relativePath = `/place_images/${placeId}/${filename}`;
        const isMain = existingImages.length === 0 && uploadedImages.length === 0 ? 1 : 0;
        maxOrder++;

        const image = await storage.addPlaceImage(placeId, relativePath, isMain, maxOrder);
        uploadedImages.push(image);
      }

      res.json({ success: true, images: uploadedImages });
    } catch (error) {
      console.error("Error uploading place images:", error);
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

      await storage.setMainPlaceImage(placeId, imageId);
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

      await storage.deletePlaceImage(imageId);
      res.json({ success: true });
    } catch (error) {
      console.error("Error deleting place image:", error);
      res.status(500).json({ error: "Failed to delete image" });
    }
  });

  // PWA Icon upload route
  app.post("/api/settings/pwa-icon", upload.single("icon"), async (req, res) => {
    try {
      if (!req.file) {
        return res.status(400).json({ error: "No file uploaded" });
      }

      const tempPath = req.file.path;
      const iconsDir = path.join(import.meta.dirname, "..", "client", "public", "icons");

      // Generate all required icon sizes using sips
      const sizes = [
        { size: 512, name: "icon-512.png" },
        { size: 192, name: "icon-192.png" },
        { size: 180, name: "apple-touch-icon.png" },
        { size: 32, name: "favicon-32.png" },
      ];

      for (const { size, name } of sizes) {
        const outputPath = path.join(iconsDir, name);
        await execAsync(`sips -z ${size} ${size} "${tempPath}" --out "${outputPath}"`);
      }

      // Generate favicon.ico using Python PIL
      const favicon32Path = path.join(iconsDir, "favicon-32.png");
      const faviconPath = path.join(import.meta.dirname, "..", "client", "public", "favicon.ico");

      await execAsync(`python3 -c "from PIL import Image; img = Image.open('${favicon32Path}'); img.save('${faviconPath}', format='ICO')"`);

      // Copy source file for future reference
      const sourcePath = path.join(iconsDir, "icon-source.png");
      await fs.copyFile(tempPath, sourcePath);

      // Clean up temp file
      await fs.unlink(tempPath);

      res.json({ success: true, message: "PWA icon updated successfully" });
    } catch (error) {
      console.error("Error uploading PWA icon:", error);
      res.status(500).json({ error: "Failed to upload icon" });
    }
  });

  const httpServer = createServer(app);

  return httpServer;
}