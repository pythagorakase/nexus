/**
 * Simplified stylised world map outline used as the MapTab background.
 *
 * Coordinates are normalised to a 1000x500 grid so they can be scaled to
 * the actual SVG viewport dimensions at render time. The goal is not
 * geographic precision but to provide a subtle land/sea silhouette that
 * matches the early prototype aesthetic.
 */

type OutlineShape = {
  id: string;
  points: Array<[number, number]>;
};

export const WORLD_OUTLINE_SHAPES: OutlineShape[] = [
  {
    id: "north-america",
    points: [
      [70, 170],
      [110, 120],
      [150, 90],
      [210, 60],
      [270, 60],
      [320, 90],
      [360, 140],
      [365, 185],
      [335, 215],
      [290, 225],
      [250, 210],
      [205, 220],
      [160, 205],
      [120, 195],
    ],
  },
  {
    id: "greenland",
    points: [
      [310, 60],
      [340, 40],
      [370, 55],
      [355, 95],
      [320, 95],
    ],
  },
  {
    id: "south-america",
    points: [
      [270, 235],
      [305, 265],
      [330, 315],
      [320, 360],
      [295, 410],
      [265, 440],
      [240, 370],
      [245, 310],
    ],
  },
  {
    id: "eurasia",
    points: [
      [360, 120],
      [410, 90],
      [470, 75],
      [540, 70],
      [610, 90],
      [670, 115],
      [715, 145],
      [750, 175],
      [780, 215],
      [790, 245],
      [760, 255],
      [705, 250],
      [660, 240],
      [615, 255],
      [575, 245],
      [540, 235],
      [505, 225],
      [470, 210],
      [430, 190],
      [395, 165],
    ],
  },
  {
    id: "middle-east",
    points: [
      [470, 210],
      [505, 230],
      [535, 255],
      [525, 285],
      [495, 295],
      [460, 265],
      [450, 235],
    ],
  },
  {
    id: "africa",
    points: [
      [420, 220],
      [455, 245],
      [485, 285],
      [480, 340],
      [455, 380],
      [420, 360],
      [400, 305],
      [405, 260],
    ],
  },
  {
    id: "india",
    points: [
      [575, 245],
      [600, 270],
      [595, 305],
      [565, 310],
      [550, 280],
    ],
  },
  {
    id: "se-asia",
    points: [
      [600, 270],
      [630, 285],
      [645, 310],
      [620, 320],
      [600, 300],
    ],
  },
  {
    id: "australia",
    points: [
      [640, 330],
      [680, 320],
      [720, 330],
      [755, 355],
      [745, 395],
      [705, 405],
      [665, 380],
      [640, 360],
    ],
  },
  {
    id: "antarctica",
    points: [
      [180, 460],
      [310, 470],
      [470, 480],
      [640, 470],
      [520, 495],
      [340, 490],
    ],
  },
];

export const BACKGROUND_NORMALISED_WIDTH = 1000;
export const BACKGROUND_NORMALISED_HEIGHT = 500;
