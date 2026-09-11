// Generated Media prepared input schemas. Regenerate from the inventoried source.
export const SDK_MEDIA_PREPARED_INPUTS = [
  {
    "actionId": "cutagent.action.media.clear_transcription",
    "inputSchema": {
      "additionalProperties": false,
      "not": {
        "required": [
          "clip",
          "folder"
        ]
      },
      "properties": {
        "clip": {
          "minLength": 1,
          "type": "string"
        },
        "folder": {
          "minLength": 1,
          "type": "string"
        }
      },
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.color.clear",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        }
      },
      "required": [
        "name"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.color.set",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "color": {
          "type": "string"
        },
        "name": {
          "type": "string"
        }
      },
      "required": [
        "color",
        "name"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.create_timeline",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clips": {
          "items": {
            "type": "string"
          },
          "maxItems": 1000,
          "minItems": 1,
          "type": "array"
        },
        "timelineName": {
          "type": "string"
        }
      },
      "required": [
        "clips",
        "timelineName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.delete",
    "inputSchema": {
      "oneOf": [
        {
          "additionalProperties": false,
          "properties": {
            "name": {
              "minLength": 1,
              "type": "string"
            }
          },
          "required": [
            "name"
          ],
          "type": "object"
        },
        {
          "additionalProperties": false,
          "properties": {
            "name": {
              "items": {
                "minLength": 1,
                "type": "string"
              },
              "maxItems": 1000,
              "minItems": 1,
              "type": "array",
              "uniqueItems": true
            }
          },
          "required": [
            "name"
          ],
          "type": "object"
        },
        {
          "additionalProperties": false,
          "properties": {
            "assetIds": {
              "items": {
                "minLength": 1,
                "type": "string"
              },
              "maxItems": 1000,
              "minItems": 1,
              "type": "array",
              "uniqueItems": true
            },
            "precondition": {
              "minLength": 1,
              "type": "string"
            },
            "projectId": {
              "minLength": 1,
              "type": "string"
            }
          },
          "required": [
            "projectId",
            "precondition",
            "assetIds"
          ],
          "type": "object"
        }
      ]
    }
  },
  {
    "actionId": "cutagent.action.media.duplicate",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        },
        "newName": {
          "type": "string"
        }
      },
      "required": [
        "name"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.extract_template",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "minLength": 1,
          "type": "string"
        },
        "exact": {
          "type": "boolean"
        },
        "fields": {
          "items": {
            "enum": [
              "text",
              "image"
            ]
          },
          "minItems": 1,
          "type": "array",
          "uniqueItems": true
        },
        "folder": {
          "minLength": 1,
          "type": "string"
        },
        "includeNested": {
          "type": "boolean"
        }
      },
      "required": [
        "clip"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.flag.add",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "color": {
          "type": "string"
        },
        "name": {
          "type": "string"
        }
      },
      "required": [
        "color",
        "name"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.flag.clear",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "color": {
          "type": "string"
        },
        "name": {
          "type": "string"
        }
      },
      "required": [
        "name"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.folder.export_drb",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "file": {
          "type": "string"
        },
        "folder": {
          "type": "string"
        }
      },
      "required": [
        "file",
        "folder"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.folder.import_drb",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "file": {
          "type": "string"
        },
        "sourceClipsPath": {
          "type": "string"
        }
      },
      "required": [
        "file"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.folders.move",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "path": {
          "type": "string"
        },
        "targetPath": {
          "type": "string"
        }
      },
      "required": [
        "path",
        "targetPath"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.folders.open",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "path": {
          "type": "string"
        }
      },
      "required": [
        "path"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.folders.root",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.growing_file.monitor",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        }
      },
      "required": [
        "clip"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.mark.clear",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "markType": {
          "enum": [
            "all",
            "video",
            "audio"
          ]
        }
      },
      "required": [
        "clip"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.mark.set",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "markIn": {
          "type": "integer"
        },
        "markOut": {
          "type": "integer"
        },
        "markType": {
          "enum": [
            "all",
            "video",
            "audio"
          ]
        }
      },
      "required": [
        "clip",
        "markIn",
        "markOut"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.marker.add",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "color": {
          "type": "string"
        },
        "duration": {
          "type": "integer"
        },
        "frame": {
          "type": "integer"
        },
        "markerName": {
          "type": "string"
        },
        "name": {
          "type": "string"
        },
        "note": {
          "type": "string"
        }
      },
      "required": [
        "frame",
        "name"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.marker.delete",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "color": {
          "type": "string"
        },
        "frame": {
          "type": "integer"
        },
        "name": {
          "type": "string"
        }
      },
      "required": [
        "name"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.matte.delete",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "paths": {
          "items": {
            "type": "string"
          },
          "maxItems": 999,
          "minItems": 1,
          "type": "array"
        }
      },
      "required": [
        "clip",
        "paths"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.metadata.export",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clips": {
          "items": {
            "type": "string"
          },
          "maxItems": 999,
          "type": "array"
        },
        "file": {
          "type": "string"
        }
      },
      "required": [
        "file"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.move",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        },
        "target": {
          "type": "string"
        }
      },
      "required": [
        "name",
        "target"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.proxy",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "minLength": 1,
          "type": "string"
        },
        "operation": {
          "oneOf": [
            {
              "additionalProperties": false,
              "properties": {
                "kind": {
                  "const": "generate"
                }
              },
              "required": [
                "kind"
              ],
              "type": "object"
            },
            {
              "additionalProperties": false,
              "properties": {
                "kind": {
                  "const": "link"
                },
                "path": {
                  "minLength": 1,
                  "type": "string"
                }
              },
              "required": [
                "kind",
                "path"
              ],
              "type": "object"
            },
            {
              "additionalProperties": false,
              "properties": {
                "kind": {
                  "const": "unlink"
                }
              },
              "required": [
                "kind"
              ],
              "type": "object"
            }
          ]
        }
      },
      "required": [
        "clipName",
        "operation"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.proxy.link_fullres",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "path": {
          "type": "string"
        }
      },
      "required": [
        "clip",
        "path"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.relink",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        },
        "path": {
          "type": "string"
        }
      },
      "required": [
        "name",
        "path"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.rename",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "new": {
          "type": "string"
        },
        "old": {
          "type": "string"
        }
      },
      "required": [
        "new",
        "old"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.replace",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "path": {
          "type": "string"
        }
      },
      "required": [
        "clip",
        "path"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.replace_preserve_subclip",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "path": {
          "type": "string"
        }
      },
      "required": [
        "clip",
        "path"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.selected.set",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        }
      },
      "required": [
        "clip"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.stereo_create",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "left": {
          "type": "string"
        },
        "right": {
          "type": "string"
        }
      },
      "required": [
        "left",
        "right"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.sync_audio",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "channel": {
          "type": "integer"
        },
        "clips": {
          "items": {
            "type": "string"
          },
          "maxItems": 1000,
          "minItems": 1,
          "type": "array"
        },
        "mode": {
          "type": "string"
        },
        "retainEmbeddedAudio": {
          "type": "boolean"
        },
        "retainVideoMetadata": {
          "type": "boolean"
        }
      },
      "required": [
        "clips"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.transcode",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "codec": {
          "type": "string"
        },
        "format": {
          "type": "string"
        },
        "name": {
          "type": "string"
        },
        "outputPath": {
          "type": "string"
        }
      },
      "required": [
        "name",
        "outputPath"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.transcribe",
    "inputSchema": {
      "additionalProperties": false,
      "oneOf": [
        {
          "required": [
            "clip"
          ]
        },
        {
          "required": [
            "folder"
          ]
        }
      ],
      "properties": {
        "clip": {
          "minLength": 1,
          "type": "string"
        },
        "folder": {
          "minLength": 1,
          "type": "string"
        },
        "language": {
          "type": "string"
        }
      },
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.unlink",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        }
      },
      "required": [
        "name"
      ],
      "type": "object"
    }
  }
];
