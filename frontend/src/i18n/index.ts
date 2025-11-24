import { en } from './en';
import { ja } from './ja';

export const TEXTS = {
  en,
  ja
};

export type Lang = keyof typeof TEXTS;
export type Translation = typeof en;
