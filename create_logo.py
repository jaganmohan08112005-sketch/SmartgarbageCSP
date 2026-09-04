import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

fig, ax = plt.subplots(figsize=(3, 3))
ax.set_xlim(0, 10)
ax.set_ylim(0, 10)
ax.axis('off')

# Outer circle
circle = plt.Circle((5, 5), 4.5, fill=False, edgecolor='#1B5E20', linewidth=3)
ax.add_patch(circle)

# Inner circle
circle2 = plt.Circle((5, 5), 3.8, fill=False, edgecolor='#1B5E20', linewidth=1.5)
ax.add_patch(circle2)

# Central lamp
ax.add_patch(patches.Rectangle((3.5, 2.5), 3, 0.4, facecolor='#1B5E20'))
ax.add_patch(patches.Rectangle((4.2, 2.9), 1.6, 2.0, facecolor='#1B5E20'))

# Flame
flame_x = [5, 4.3, 5.7, 5]
flame_y = [6.5, 5.2, 5.2, 6.5]
ax.fill(flame_x, flame_y, color='#FFD700')

# College name
ax.text(5, 8.8, 'MAHARAJ VIJAYARAM', ha='center', va='center', fontsize=6, fontweight='bold', color='#1B5E20')
ax.text(5, 8.2, 'GAJAPATHI RAJ', ha='center', va='center', fontsize=6, fontweight='bold', color='#1B5E20')
ax.text(5, 7.6, 'COLLEGE OF ENGINEERING', ha='center', va='center', fontsize=5.5, fontweight='bold', color='#1B5E20')
ax.text(5, 7.1, '(Autonomous)', ha='center', va='center', fontsize=5, color='#1B5E20')

# Bottom text
ax.text(5, 1.5, 'VIZIANAGARAM', ha='center', va='center', fontsize=6, fontweight='bold', color='#1B5E20')
ax.text(5, 1.0, 'Estd. 1997', ha='center', va='center', fontsize=5, fontstyle='italic', color='#1B5E20')

plt.tight_layout()
plt.savefig('_diagrams/mvgr_logo.png', dpi=200, bbox_inches='tight', facecolor='white', edgecolor='none')
plt.close()
print('MVGR logo created')
